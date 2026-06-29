from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from atlas_api import config
from atlas_api.main import create_app


@pytest_asyncio.fixture
async def app_client(
    pg_engine: AsyncEngine, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://placeholder/db")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret-test-secret")
    config.get_settings.cache_clear()
    app = create_app(engine=pg_engine, redis_url=redis_url)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            yield client


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/v1/auth/register", json={"email": email, "password": "supersecret12"})
    r = await client.post("/v1/auth/login", json={"email": email, "password": "supersecret12"})
    return str(r.json()["access_token"])


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
