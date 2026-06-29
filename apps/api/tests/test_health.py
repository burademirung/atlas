import pytest
from httpx import ASGITransport, AsyncClient

from atlas_api.main import create_app


@pytest.fixture
def client() -> AsyncClient:
    app = create_app()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_healthz(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["x-request-id"]


async def test_problem_json_shape(client: AsyncClient) -> None:
    # unknown route -> FastAPI 404, but our handler must emit problem+json
    resp = await client.get("/v1/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 404
    assert "title" in body
