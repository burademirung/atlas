"""Per-run progress streaming over Redis Streams + cooperative cancellation.

Workers ``XADD`` events to a per-run stream; the SSE endpoint replays the stream
from ``Last-Event-ID`` and then tails it live. A separate Redis key is the
cancel flag the worker checks between graph supersteps.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

TERMINAL_EVENTS = {"done", "error", "cancelled"}


def stream_key(run_id: int) -> str:
    return f"atlas:run:{run_id}:events"


def cancel_key(run_id: int) -> str:
    return f"atlas:run:{run_id}:cancel"


async def emit(redis: Redis, run_id: int, event: str, data: dict[str, Any]) -> None:
    await redis.xadd(
        stream_key(run_id),
        {"event": event, "data": json.dumps(data)},
        maxlen=2000,
        approximate=True,
    )


async def request_cancel(redis: Redis, run_id: int) -> None:
    await redis.set(cancel_key(run_id), "1", ex=3600)


async def is_cancelled(redis: Redis, run_id: int) -> bool:
    return bool(await redis.exists(cancel_key(run_id)))


async def sse_events(
    redis: Redis, run_id: int, last_id: str = "0", *, block_ms: int = 15000
) -> AsyncIterator[str]:
    """Yield SSE frames for a run: replay from ``last_id``, then tail live.

    Stops after a terminal event (done/error/cancelled). Emits comment
    heartbeats while idle so proxies don't drop the connection.
    """
    start = last_id or "0"
    while True:
        resp = await redis.xread({stream_key(run_id): start}, block=block_ms, count=100)
        if not resp:
            yield ": keepalive\n\n"
            continue
        for _stream, entries in resp:
            for entry_id, fields in entries:
                start = entry_id
                event = fields.get("event", "message")
                data = fields.get("data", "{}")
                yield f"id: {entry_id}\nevent: {event}\ndata: {data}\n\n"
                if event in TERMINAL_EVENTS:
                    return
