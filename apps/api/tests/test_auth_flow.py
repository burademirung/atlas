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
    # The lifespan reads Settings at startup; provide the mandatory fields. The engine and
    # redis_url passed to create_app() override database_url/redis_url, so those are placeholders.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://placeholder/db")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret-test-secret")
    config.get_settings.cache_clear()
    app = create_app(engine=pg_engine, redis_url=redis_url)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            yield client


async def test_register_login_refresh_logout(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/v1/auth/register", json={"email": "flow@example.com", "password": "supersecret12"}
    )
    assert r.status_code == 201
    assert r.json()["email"] == "flow@example.com"

    r = await app_client.post(
        "/v1/auth/login", json={"email": "flow@example.com", "password": "supersecret12"}
    )
    assert r.status_code == 200
    tokens = r.json()
    access, refresh = tokens["access_token"], tokens["refresh_token"]

    r = await app_client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert r.json()["access_token"] != access

    r = await app_client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 204


async def test_login_wrong_password_is_401_problem(app_client: AsyncClient) -> None:
    await app_client.post(
        "/v1/auth/register", json={"email": "z@example.com", "password": "supersecret12"}
    )
    r = await app_client.post("/v1/auth/login", json={"email": "z@example.com", "password": "nope"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
