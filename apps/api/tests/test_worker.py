from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from atlas_api.agents import StubSearchProvider
from atlas_api.config import Settings
from atlas_api.db.engine import session_factory
from atlas_api.db.models import RunStatus, User
from atlas_api.runs import streaming
from atlas_api.runs.repository import RunRepository
from atlas_api.worker import _data_types, run_research_job


class _UsageModel:
    """Chat model that reports fixed token usage, to exercise the run token cap."""

    def __init__(self, responses: list[str], per_call_tokens: int) -> None:
        self._responses = list(responses)
        self._tokens = per_call_tokens

    async def ainvoke(self, messages: list[Any], **_: Any) -> AIMessage:
        content = self._responses.pop(0)
        return AIMessage(
            content=content,
            usage_metadata={
                "input_tokens": self._tokens,
                "output_tokens": self._tokens,
                "total_tokens": self._tokens * 2,
            },
        )


PLAN = "Newest battery chemistries?\nHighest energy density options?\nSafety tradeoffs?"
VERIFY = "Relevant: 1, 2, 3, 4, 5, 6"
REPORT = "## Findings\nSolid-state leads [1].\n\n## Sources\n[1] ..."


def _settings(redis_url: str) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url=redis_url,
        jwt_secret="s" * 32,
        max_subquestions=4,
        max_sources_per_q=2,
    )


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()


async def test_worker_runs_graph_persists_and_streams(
    pg_engine: AsyncEngine, redis_client: Redis, redis_url: str
) -> None:
    maker = session_factory(pg_engine)
    async with maker() as session:
        user = User(email="worker@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        run = await RunRepository(session).create(user.id, "Newest EV battery chemistries?")
        run_id = run.id
        await session.commit()

    ctx = {
        "redis": redis_client,
        "sessionmaker": maker,
        "settings": _settings(redis_url),
        "model": FakeListChatModel(responses=[PLAN, VERIFY, REPORT]),
        "provider": StubSearchProvider(),
    }
    result = await run_research_job(ctx, run_id)
    assert result["status"] == "done"

    # persisted
    async with maker() as session:
        repo = RunRepository(session)
        persisted = await repo.get(run_id)
        assert persisted is not None
        assert persisted.status == RunStatus.done
        report = await repo.report_for_run(run_id)
        assert report is not None and report.markdown == REPORT
        sources = await repo.sources_for_run(run_id)
        assert len(sources) == 6

    # streamed
    entries = await redis_client.xrange(streaming.stream_key(run_id))
    events = [fields["event"] for _id, fields in entries]
    assert "plan" in events
    assert events.count("source") == 6
    assert events[-1] == "done"


async def test_worker_cancellation(
    pg_engine: AsyncEngine, redis_client: Redis, redis_url: str
) -> None:
    maker = session_factory(pg_engine)
    async with maker() as session:
        user = User(email="cancel@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        run = await RunRepository(session).create(user.id, "Cancel me")
        run_id = run.id
        await session.commit()

    await streaming.request_cancel(redis_client, run_id)  # pre-cancel

    ctx = {
        "redis": redis_client,
        "sessionmaker": maker,
        "settings": _settings(redis_url),
        "model": FakeListChatModel(responses=[PLAN, VERIFY, REPORT]),
        "provider": StubSearchProvider(),
    }
    result = await run_research_job(ctx, run_id)
    assert result["status"] == "cancelled"
    async with maker() as session:
        persisted = await RunRepository(session).get(run_id)
        assert persisted is not None and persisted.status == RunStatus.cancelled


def test_data_types_helper_parses_config() -> None:
    assert _data_types(None) == []
    assert _data_types({}) == []
    assert _data_types({"data_types": ["ssn", "email"]}) == ["ssn", "email"]
    assert _data_types({"data_types": "not-a-list"}) == []


async def test_worker_truncates_when_token_cap_exceeded(
    pg_engine: AsyncEngine, redis_client: Redis, redis_url: str
) -> None:
    maker = session_factory(pg_engine)
    async with maker() as session:
        user = User(email="cap@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        run = await RunRepository(session).create(user.id, "Spend a lot")
        run_id = run.id
        await session.commit()

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url=redis_url,
        jwt_secret="s" * 32,
        max_sources_per_q=2,
        max_run_tokens=1000,
    )
    # The plan node alone reports 2_000 tokens, over the 1_000 ceiling, so the
    # run is truncated before search/verify/write run.
    ctx = {
        "redis": redis_client,
        "sessionmaker": maker,
        "settings": settings,
        "model": _UsageModel([PLAN, VERIFY, REPORT], per_call_tokens=1000),
        "provider": StubSearchProvider(),
    }
    result = await run_research_job(ctx, run_id)
    assert result["status"] == "truncated"
    assert result["tokens"] >= 1000
    async with maker() as session:
        repo = RunRepository(session)
        persisted = await repo.get(run_id)
        assert persisted is not None and persisted.status == RunStatus.truncated
        assert persisted.tokens_used >= 1000

    events = [f["event"] for _id, f in await redis_client.xrange(streaming.stream_key(run_id))]
    assert events[-1] == "truncated"


async def test_worker_lifecycle_helpers(
    postgres_url: str, redis_url: str, monkeypatch: Any
) -> None:
    from atlas_api import worker

    settings = Settings(
        database_url=postgres_url,
        redis_url=redis_url,
        jwt_secret="s" * 32,
        anthropic_api_key="sk-test",
    )
    monkeypatch.setattr(worker, "get_settings", lambda: settings)

    ctx: dict[str, Any] = {}
    await worker.on_startup(ctx)
    assert "engine" in ctx and "sessionmaker" in ctx and "provider" in ctx
    assert "model" in ctx  # built because a key was provided
    await worker.on_shutdown(ctx)
    await worker.on_shutdown({})  # no engine -> safe no-op

    assert worker._redis_settings() is not None
    assert worker._build_model(settings) is not None
