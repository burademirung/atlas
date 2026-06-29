import pytest
import pytest_asyncio
from redis.asyncio import Redis

from atlas_api.auth.tokens import TokenService
from atlas_api.config import Settings
from atlas_api.errors import ProblemException


def make_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_secret="s" * 32,
    )


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> Redis:
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    return client


async def test_issue_and_decode_access(redis_client: Redis) -> None:
    svc = TokenService(make_settings(), redis_client)
    pair = svc.issue_pair(user_id=42)
    claims = svc.decode(pair.access, expected_typ="access")
    assert claims.sub == "42"
    assert claims.typ == "access"


async def test_decode_rejects_wrong_type(redis_client: Redis) -> None:
    svc = TokenService(make_settings(), redis_client)
    pair = svc.issue_pair(user_id=1)
    with pytest.raises(ProblemException):
        svc.decode(pair.refresh, expected_typ="access")


async def test_refresh_reuse_revokes_family(redis_client: Redis) -> None:
    svc = TokenService(make_settings(), redis_client)
    pair = svc.issue_pair(user_id=7)
    # first rotation succeeds
    new_pair = await svc.rotate_refresh(pair.refresh)
    assert new_pair.refresh != pair.refresh
    # reusing the original (now-used) refresh must fail
    with pytest.raises(ProblemException):
        await svc.rotate_refresh(pair.refresh)
    # and the family is revoked, so the freshly-issued one is now dead too
    with pytest.raises(ProblemException):
        await svc.rotate_refresh(new_pair.refresh)
