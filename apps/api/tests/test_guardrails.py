from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from starlette.requests import Request

from atlas_api.errors import ProblemException
from atlas_api.security import guardrails


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()


def _request(headers: dict[str, str] | None = None, client_host: str | None = "1.2.3.4") -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/runs",
        "headers": raw_headers,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_check_service_paused() -> None:
    guardrails.check_service_paused(False)  # no raise
    with pytest.raises(ProblemException) as ei:
        guardrails.check_service_paused(True)
    assert ei.value.status == 503


def test_client_ip_reads_trusted_hop_from_right_not_spoofable_left() -> None:
    # XFF = "client, proxy"; with one trusted proxy the real client is the
    # right-most-but-one. A spoofed left-most value must be ignored.
    req = _request(headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
    assert guardrails.client_ip(req, trusted_proxy_count=1) == "10.0.0.1"
    # An attacker prepending a fake hop cannot change the trusted offset result.
    spoof = _request(headers={"x-forwarded-for": "1.1.1.1, 2.2.2.2, 3.3.3.3"})
    assert guardrails.client_ip(spoof, trusted_proxy_count=1) == "3.3.3.3"


def test_client_ip_zero_trusted_proxies_uses_socket_peer() -> None:
    req = _request(headers={"x-forwarded-for": "9.9.9.9"})
    assert guardrails.client_ip(req, trusted_proxy_count=0) == "1.2.3.4"


def test_client_ip_falls_back_to_peer_then_unknown() -> None:
    assert guardrails.client_ip(_request()) == "1.2.3.4"
    assert guardrails.client_ip(_request(client_host=None)) == "unknown"
    # Non-IP garbage in XFF is rejected, falling back to the socket peer.
    bad = _request(headers={"x-forwarded-for": "not-an-ip"})
    assert guardrails.client_ip(bad, trusted_proxy_count=1) == "1.2.3.4"


def test_over_token_cap() -> None:
    assert guardrails.over_token_cap(100, 100) is True
    assert guardrails.over_token_cap(99, 100) is False
    assert guardrails.over_token_cap(100, 0) is False  # 0 disables the cap


async def test_enforce_daily_quota_user_limit(redis_client: Redis) -> None:
    for _ in range(3):
        await guardrails.enforce_daily_quota(
            redis_client, user_id=1, ip="1.1.1.1", user_limit=3, ip_limit=100
        )
    with pytest.raises(ProblemException) as ei:
        await guardrails.enforce_daily_quota(
            redis_client, user_id=1, ip="1.1.1.1", user_limit=3, ip_limit=100
        )
    assert ei.value.status == 429
    # a different user is unaffected
    await guardrails.enforce_daily_quota(
        redis_client, user_id=2, ip="2.2.2.2", user_limit=3, ip_limit=100
    )


async def test_enforce_daily_quota_ip_limit(redis_client: Redis) -> None:
    # distinct users, same IP -> IP ceiling trips
    await guardrails.enforce_daily_quota(
        redis_client, user_id=10, ip="5.5.5.5", user_limit=100, ip_limit=1
    )
    with pytest.raises(ProblemException) as ei:
        await guardrails.enforce_daily_quota(
            redis_client, user_id=11, ip="5.5.5.5", user_limit=100, ip_limit=1
        )
    assert ei.value.status == 429


async def test_quota_counter_expires_at_midnight(redis_client: Redis) -> None:
    now = datetime(2026, 6, 29, 23, 59, 0, tzinfo=UTC)
    await guardrails.enforce_daily_quota(
        redis_client, user_id=7, ip="3.3.3.3", user_limit=5, ip_limit=5, now=now
    )
    ttl = await redis_client.ttl(f"quota:user:7:{now.date().isoformat()}")
    assert 0 < ttl <= 60


async def test_idempotency_roundtrip(redis_client: Redis) -> None:
    assert await guardrails.idempotent_run_id(redis_client, 1, "k1") is None
    await guardrails.remember_idempotent_run(redis_client, 1, "k1", 42, ttl=60)
    assert await guardrails.idempotent_run_id(redis_client, 1, "k1") == 42
    # set-if-absent: a second remember does not overwrite the first run id
    await guardrails.remember_idempotent_run(redis_client, 1, "k1", 99, ttl=60)
    assert await guardrails.idempotent_run_id(redis_client, 1, "k1") == 42
