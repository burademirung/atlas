# ADR 0003 — SSE backed by Redis Streams, not pub/sub

**Status:** Accepted · 2026-06-29

## Context

A research run takes minutes and emits a sequence of events (planning → searching → sources →
writing → done) that the browser watches live. Requirements:

- **Streaming** to the browser (chosen transport: **SSE** — Cloudflare-friendly, simple, one-way).
- **Lossless reconnect:** a dropped connection (mobile, proxy timeout) must resume without losing
  events emitted while disconnected.
- **No sticky sessions:** the run executes in a *worker* pod, but the SSE connection terminates on
  any *API* pod — so the transport must be shared state, not in-process.

Redis **pub/sub** is fire-and-forget: a subscriber that isn't connected at publish time misses the
message permanently. That fails the reconnect requirement.

## Decision

Use **Redis Streams** as the per-run streaming backbone, with **SSE** to the browser.

- Workers `XADD` events to a per-run stream `atlas:run:<id>:events` (capped `maxlen ~2000`)
  ([`apps/api/src/atlas_api/runs/streaming.py`](../../apps/api/src/atlas_api/runs/streaming.py)).
- The SSE endpoint **replays** from the client's `Last-Event-ID` and then **tails live** via
  `XREAD BLOCK`, emitting each entry as an SSE frame with `id: <entry>` for the next reconnect.
- Any API pod can serve any client (no sticky sessions); heartbeat comments keep idle connections
  open. Gaps older than stream retention can be replayed from the persisted `run_steps` table.

## Consequences

- **+** **Lossless reconnect** within retention via `Last-Event-ID` — the core requirement pub/sub
  couldn't meet.
- **+** Stateless API pods → clean horizontal scaling and rollouts (combined with `maxUnavailable:
  0` + SSE drain, in-flight streams survive deploys).
- **+** The stream doubles as a short-term audit/telemetry log of the run.
- **−** Streams retain data (memory) where pub/sub wouldn't; bounded by `maxlen` + run-scoped keys.
- **−** Reconnect gaps **longer than retention** require the `run_steps` replay path (a second code
  path), and retention must be sized against expected disconnect windows.
- **−** SSE is one-way; cancellation uses a separate Redis flag (`atlas:run:<id>:cancel`) the worker
  checks between supersteps, not the stream.
