from collections.abc import AsyncIterator

import pytest_asyncio
from redis.asyncio import Redis

from atlas_api.runs import streaming


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()


async def test_sse_events_replays_until_terminal(redis_client: Redis) -> None:
    run_id = 4242
    await streaming.emit(redis_client, run_id, "status", {"phase": "planning"})
    await streaming.emit(redis_client, run_id, "done", {"id": run_id})

    frames = [frame async for frame in streaming.sse_events(redis_client, run_id, "0")]
    joined = "".join(frames)
    assert "event: status" in joined
    assert "event: done" in joined
    # Generator returns right after the terminal event.
    assert frames[-1].strip().endswith("}")


async def test_sse_events_emits_keepalive_when_idle(redis_client: Redis) -> None:
    gen = streaming.sse_events(redis_client, 7, "0", block_ms=50)
    frame = await anext(gen)
    assert frame == ": keepalive\n\n"
    await gen.aclose()
