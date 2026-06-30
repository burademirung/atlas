from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> None:
    await client.post("/v1/auth/register", json={"email": email, "password": "supersecret12"})


async def test_duplicate_email_is_409(app_client: AsyncClient) -> None:
    await _register(app_client, "dup-edge@example.com")
    r = await app_client.post(
        "/v1/auth/register", json={"email": "dup-edge@example.com", "password": "supersecret12"}
    )
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_revoked_access_token_is_rejected(app_client: AsyncClient) -> None:
    await _register(app_client, "revoke@example.com")
    r = await app_client.post(
        "/v1/auth/login", json={"email": "revoke@example.com", "password": "supersecret12"}
    )
    access = r.json()["access_token"]
    h = {"Authorization": f"Bearer {access}"}

    # token works before logout
    assert (await app_client.get("/v1/runs", headers=h)).status_code == 200
    # logout revokes it
    assert (await app_client.post("/v1/auth/logout", headers=h)).status_code == 204
    # subsequent use is rejected (deps.get_current_user revocation path)
    assert (await app_client.get("/v1/runs", headers=h)).status_code == 401


async def test_malformed_bearer_is_401(app_client: AsyncClient) -> None:
    r = await app_client.get("/v1/runs", headers={"Authorization": "Token abc"})
    assert r.status_code == 401
