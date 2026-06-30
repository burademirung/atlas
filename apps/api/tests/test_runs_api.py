from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncEngine

from atlas_api import config
from atlas_api.agents import StubSearchProvider
from atlas_api.db.engine import session_factory
from atlas_api.db.models import ResearchRun
from atlas_api.main import create_app

PLAN = "Freeze your credit immediately?\nReport the SSN exposure where?\nMonitor what?"
VERIFY = "Relevant: 1, 2"
REPORT = "## Do this now\n- [ ] Freeze credit [1]\n\n## Sources\n[1] ..."


class RecordingModel:
    """Duck-typed chat model: returns scripted text, records the prompts it sees."""

    def __init__(self, responses: list[str], usage: dict[str, int] | None = None) -> None:
        self._responses = list(responses)
        self.calls: list[list[Any]] = []
        self._usage = usage

    async def ainvoke(self, messages: list[Any], **_: Any) -> AIMessage:
        self.calls.append(messages)
        content = self._responses.pop(0)
        return AIMessage(content=content, usage_metadata=self._usage)  # type: ignore[arg-type]


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/v1/auth/register", json={"email": email, "password": "supersecret12"})
    r = await client.post("/v1/auth/login", json={"email": email, "password": "supersecret12"})
    return str(r.json()["access_token"])


@asynccontextmanager
async def _client_with_env(
    pg_engine: AsyncEngine,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
    **env: str,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://placeholder/db")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret-test-secret")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.get_settings.cache_clear()
    app = create_app(engine=pg_engine, redis_url=redis_url)
    async with app.router.lifespan_context(app):
        # test_config.py reloads the config module, which desyncs the lru_cache
        # that main.py's imported get_settings holds; rebuild settings from the
        # current env so guardrail overrides reliably take effect here.
        app.state.settings = config.Settings()  # type: ignore[call-arg]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            yield client
    config.get_settings.cache_clear()


async def test_create_list_get_run(app_client: AsyncClient) -> None:
    token = await _token(app_client, "runs1@example.com")
    h = {"Authorization": f"Bearer {token}"}

    r = await app_client.post("/v1/runs", json={"question": "Why is the sky blue?"}, headers=h)
    assert r.status_code == 202
    run = r.json()
    assert run["status"] == "queued"
    run_id = run["id"]

    r = await app_client.get("/v1/runs", headers=h)
    assert r.status_code == 200
    assert any(x["id"] == run_id for x in r.json())

    r = await app_client.get(f"/v1/runs/{run_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["question"] == "Why is the sky blue?"


async def test_run_is_tenant_isolated(app_client: AsyncClient) -> None:
    owner_h = {"Authorization": f"Bearer {await _token(app_client, 'owner@example.com')}"}
    other_h = {"Authorization": f"Bearer {await _token(app_client, 'other@example.com')}"}

    r = await app_client.post("/v1/runs", json={"question": "private question"}, headers=owner_h)
    run_id = r.json()["id"]

    # another user cannot read it
    r = await app_client.get(f"/v1/runs/{run_id}", headers=other_h)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")

    # and cannot cancel it
    r = await app_client.post(f"/v1/runs/{run_id}/cancel", headers=other_h)
    assert r.status_code == 404


async def test_create_requires_auth(app_client: AsyncClient) -> None:
    r = await app_client.post("/v1/runs", json={"question": "no auth"})
    assert r.status_code == 401


async def test_question_pii_is_redacted_before_persist(
    app_client: AsyncClient, pg_engine: AsyncEngine
) -> None:
    token = await _token(app_client, "pii@example.com")
    h = {"Authorization": f"Bearer {token}"}
    r = await app_client.post(
        "/v1/runs",
        json={"question": "My SSN 123-45-6789 leaked, what now?"},
        headers=h,
    )
    assert r.status_code == 202
    assert "123-45-6789" not in r.json()["question"]
    assert "[redacted-ssn]" in r.json()["question"]


async def test_data_types_reach_write_node_on_api_path(
    app_client: AsyncClient, pg_engine: AsyncEngine, redis_url: str
) -> None:
    """End-to-end proof: POST /v1/runs with data_types persists them and the
    worker injects the matching breach playbook into the writer's prompt."""
    from redis.asyncio import Redis

    from atlas_api.config import Settings
    from atlas_api.worker import run_research_job

    token = await _token(app_client, "dt@example.com")
    h = {"Authorization": f"Bearer {token}"}
    r = await app_client.post(
        "/v1/runs",
        json={"question": "My SSN was in a breach", "data_types": ["ssn"]},
        headers=h,
    )
    assert r.status_code == 202
    run_id = r.json()["id"]

    # data_types were persisted on the run record's config.
    maker = session_factory(pg_engine)
    async with maker() as session:
        run = await session.get(ResearchRun, run_id)
        assert run is not None
        assert run.config == {"data_types": ["ssn"]}

    # Drive the worker job with a recording model and assert the SSN playbook
    # text landed in the write node's prompt.
    model = RecordingModel([PLAN, VERIFY, REPORT])
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        settings = Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            redis_url=redis_url,
            jwt_secret="s" * 32,
            max_sources_per_q=2,
        )
        ctx = {
            "redis": redis,
            "sessionmaker": maker,
            "settings": settings,
            "model": model,
            "provider": StubSearchProvider(),
        }
        result = await run_research_job(ctx, run_id)
    finally:
        await redis.aclose()

    assert result["status"] == "done"
    write_prompt = model.calls[-1][-1].content
    assert "INTERNAL PLAYBOOKS" in write_prompt
    assert "credit" in write_prompt.lower()  # ssn playbook content


async def test_idempotency_key_dedupes_submission(app_client: AsyncClient) -> None:
    token = await _token(app_client, "idem@example.com")
    h = {"Authorization": f"Bearer {token}", "Idempotency-Key": "abc-123"}

    r1 = await app_client.post("/v1/runs", json={"question": "dedupe me please"}, headers=h)
    r2 = await app_client.post("/v1/runs", json={"question": "dedupe me please"}, headers=h)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["id"] == r2.json()["id"]

    # a different key starts a fresh run
    h2 = {"Authorization": f"Bearer {token}", "Idempotency-Key": "different"}
    r3 = await app_client.post("/v1/runs", json={"question": "dedupe me please"}, headers=h2)
    assert r3.json()["id"] != r1.json()["id"]


async def test_service_paused_returns_503(
    pg_engine: AsyncEngine, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _client_with_env(pg_engine, redis_url, monkeypatch, SERVICE_PAUSED="true") as client:
        token = await _token(client, "paused@example.com")
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post("/v1/runs", json={"question": "are we open?"}, headers=h)
        assert r.status_code == 503
        assert r.headers["content-type"].startswith("application/problem+json")


async def test_run_detail_events_and_cancel_after_worker(
    app_client: AsyncClient, pg_engine: AsyncEngine, redis_url: str
) -> None:
    """Run a job to completion, then read the detail + SSE event stream + cancel."""
    from redis.asyncio import Redis

    from atlas_api.config import Settings
    from atlas_api.worker import run_research_job

    token = await _token(app_client, "detail@example.com")
    h = {"Authorization": f"Bearer {token}"}
    r = await app_client.post("/v1/runs", json={"question": "what happened?"}, headers=h)
    run_id = r.json()["id"]

    maker = session_factory(pg_engine)
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        settings = Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            redis_url=redis_url,
            jwt_secret="s" * 32,
            max_sources_per_q=2,
        )
        ctx = {
            "redis": redis,
            "sessionmaker": maker,
            "settings": settings,
            "model": RecordingModel([PLAN, VERIFY, REPORT]),
            "provider": StubSearchProvider(),
        }
        await run_research_job(ctx, run_id)
    finally:
        await redis.aclose()

    # detail now carries the persisted report + sources
    detail = await app_client.get(f"/v1/runs/{run_id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["report"] == REPORT
    assert len(detail.json()["sources"]) > 0

    # the SSE replay terminates on the worker's "done" event
    events = await app_client.get(f"/v1/runs/{run_id}/events", headers={**h, "Last-Event-ID": "0"})
    assert events.status_code == 200
    assert "event: done" in events.text

    # cancelling an owned run is accepted
    cancel = await app_client.post(f"/v1/runs/{run_id}/cancel", headers=h)
    assert cancel.status_code == 202

    # unknown run id -> 404
    missing = await app_client.get("/v1/runs/999999", headers=h)
    assert missing.status_code == 404


async def test_daily_quota_returns_429(
    pg_engine: AsyncEngine, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _client_with_env(pg_engine, redis_url, monkeypatch, DAILY_RUN_QUOTA="1") as client:
        token = await _token(client, "quota@example.com")
        h = {"Authorization": f"Bearer {token}"}
        r1 = await client.post("/v1/runs", json={"question": "first run ok"}, headers=h)
        assert r1.status_code == 202
        r2 = await client.post("/v1/runs", json={"question": "second is over"}, headers=h)
        assert r2.status_code == 429
