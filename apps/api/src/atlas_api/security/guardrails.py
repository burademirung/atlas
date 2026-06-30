"""Denial-of-wallet guardrails for the research API.

A breach-response copilot that fans every request out to an LLM + web search is
a textbook OWASP LLM Top-10 **LLM10 (Unbounded Consumption / Denial-of-Wallet)**
target: one abusive client can run up an unbounded model bill. These helpers add
the cheap, layered controls that bound that blast radius:

  * a global kill-switch (``SERVICE_PAUSED``) for incident containment;
  * per-user and per-IP **daily run quotas** (rate/spend limiting, ASVS V11.1);
  * **idempotency keys** so a retried or double-clicked submission is charged
    once, not twice;
  * a per-run **token ceiling** enforced across graph supersteps.

All state lives in Redis with TTLs so it is self-expiring and shared across API
replicas. Quotas fail closed on the *limit*, open on Redis errors are the
caller's responsibility — here we simply surface the counts.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime

from redis.asyncio import Redis
from starlette.requests import Request

from atlas_api.errors import ProblemException


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def client_ip(request: Request, trusted_proxy_count: int = 1) -> str:
    """Resolve the source IP used for rate-limit/quota keys, spoof-resistant.

    ``X-Forwarded-For`` is a list ``client, proxy1, ..., proxyN`` where the
    *left-most* entries are attacker-controlled: a client can prepend arbitrary
    values and a trusted proxy (the ALB) only ever appends. Trusting the
    left-most value lets anyone forge a fresh key per request and bypass the
    per-IP daily quota — i.e. defeat the denial-of-wallet guardrail.

    We therefore trust only ``trusted_proxy_count`` hops appended by our own
    infrastructure and read the IP at that offset from the **right**. With one
    trusted proxy (the ALB) that is the last element. ``trusted_proxy_count <= 0``
    ignores the header entirely and uses the socket peer. The value is validated
    as a real IP; anything else falls back to ``request.client.host``.

    The robust deployment posture is to bind Uvicorn's ``--forwarded-allow-ips``
    (or ``ProxyHeadersMiddleware``) to the VPC CIDR so the socket peer is already
    correct; this parsing is the defence-in-depth fallback.
    """
    peer = request.client.host if request.client is not None else "unknown"
    if trusted_proxy_count <= 0:
        return peer
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= trusted_proxy_count:
            candidate = parts[-trusted_proxy_count]
            if _is_ip(candidate):
                return candidate
    return peer


def _seconds_until_utc_midnight(now: datetime) -> int:
    end = datetime(now.year, now.month, now.day, tzinfo=UTC)
    elapsed = (now - end).total_seconds()
    return max(1, int(86_400 - elapsed))


def check_service_paused(paused: bool) -> None:
    """Raise 503 when the global kill-switch is engaged (OWASP LLM10)."""
    if paused:
        raise ProblemException(
            503,
            "Service temporarily paused",
            "Run submission is paused by an operator; please retry later.",
        )


async def _bump_quota(redis: Redis, key: str, limit: int, ttl: int) -> int:
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, ttl)
    return count


async def enforce_daily_quota(
    redis: Redis,
    *,
    user_id: int,
    ip: str,
    user_limit: int,
    ip_limit: int,
    now: datetime | None = None,
) -> None:
    """Increment and check the per-user and per-IP daily counters.

    Raises ``ProblemException(429)`` once either ceiling is reached. Counters
    auto-expire at the next UTC midnight so the window is a calendar day.
    """
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    ttl = _seconds_until_utc_midnight(now)

    user_count = await _bump_quota(redis, f"quota:user:{user_id}:{day}", user_limit, ttl)
    if user_count > user_limit:
        raise ProblemException(
            429,
            "Daily run quota exceeded",
            f"User limit of {user_limit} runs/day reached; resets at 00:00 UTC.",
        )
    ip_count = await _bump_quota(redis, f"quota:ip:{ip}:{day}", ip_limit, ttl)
    if ip_count > ip_limit:
        raise ProblemException(
            429,
            "Daily run quota exceeded",
            f"IP limit of {ip_limit} runs/day reached; resets at 00:00 UTC.",
        )


def _idem_key(user_id: int, key: str) -> str:
    return f"idem:run:{user_id}:{key}"


async def idempotent_run_id(redis: Redis, user_id: int, key: str) -> int | None:
    """Return the run id a prior request with this Idempotency-Key created, if any."""
    value = await redis.get(_idem_key(user_id, key))
    return int(value) if value is not None else None


async def remember_idempotent_run(
    redis: Redis, user_id: int, key: str, run_id: int, ttl: int
) -> None:
    """Record the run id for an Idempotency-Key so retries dedupe (set-if-absent)."""
    await redis.set(_idem_key(user_id, key), run_id, ex=ttl, nx=True)


def over_token_cap(used: int, cap: int) -> bool:
    """True when cumulative run token usage has reached the per-run ceiling."""
    return cap > 0 and used >= cap
