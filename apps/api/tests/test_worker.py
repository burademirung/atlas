from collections.abc import AsyncIterator

import pytest_asyncio
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from atlas_api.agents import StubSearchProvider
from atlas_api.config import Settings
from atlas_api.db.engine import session_factory
from atlas_api.db.models import RunStatus, User
from atlas_api.runs import streaming
from atlas_api.runs.repository import RunRepository
from atlas_api.worker import run_research_job

PLAN = "Newest battery chemistries?\nHighest energy density options?\nSafety tradeoffs?"
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
        "model": FakeListChatModel(responses=[PLAN, REPORT]),
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
        "model": FakeListChatModel(responses=[PLAN, REPORT]),
        "provider": StubSearchProvider(),
    }
    result = await run_research_job(ctx, run_id)
    assert result["status"] == "cancelled"
    async with maker() as session:
        persisted = await RunRepository(session).get(run_id)
        assert persisted is not None and persisted.status == RunStatus.cancelled
