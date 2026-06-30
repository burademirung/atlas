# API Reference

> The HTTP surfaces of both editions: the live Cloudflare Worker (`/api/*`) and the production
> FastAPI service (`/v1/*`), plus the SSE event shapes. Routes verified against the source.

## Table of contents

- [OpenAPI](#openapi)
- [Live Worker API (`apps/cloudflare`)](#live-worker-api-appscloudflare)
- [Production API (`apps/api`)](#production-api-appsapi)
- [SSE event shapes](#sse-event-shapes)
- [Error format](#error-format)

## OpenAPI

The production FastAPI app self-documents per the [OpenAPI](https://www.openapis.org/)
specification. With the API running (e.g. `docker compose up`):

- Swagger UI — <http://localhost:8080/docs>
- ReDoc — <http://localhost:8080/redoc>
- Raw schema — <http://localhost:8080/openapi.json>

The app is titled `Atlas API`, version `0.1.0` ([`main.py`](../apps/api/src/atlas_api/main.py)).
The live Cloudflare Worker does **not** serve an OpenAPI document — its surface is the small set of
`/api/*` routes documented below.

## Live Worker API (`apps/cloudflare`)

Source: [`apps/cloudflare/src/index.ts`](../apps/cloudflare/src/index.ts). Base URL of the deployed
edition: <https://atlas-research.burademirung.workers.dev>. Any path not matching the routes below
is served from static SPA assets (`ASSETS` binding, SPA fallback).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + whether the Anthropic key is configured |
| GET | `/api/config` | Whether Turnstile is enabled + the sitekey (for the SPA) |
| POST | `/api/research` | Run a breach-recovery analysis; **streams SSE** |
| GET | `/api/runs` | List the 25 most recent runs |
| GET | `/api/runs/:id` | One run + its sources |
| DELETE | `/api/runs/:id` | Self-service erasure of a run + its sources (`204`) |

### `GET /api/health`

```json
{ "status": "ok", "model": "claude-opus-4-8", "key": "set" }
```

### `GET /api/config`

```json
{ "turnstile": false, "sitekey": null }
```

### `POST /api/research`

Request body:

```json
{
  "question": "My debit card number was exposed in a breach. What now?",
  "dataTypes": ["financial"],
  "turnstileToken": "<token if Turnstile enabled>"
}
```

- `question` — required, **≤ 500 chars** (longer is rejected).
- `dataTypes` — optional string array; appended to the user message to tailor the plan.
- `turnstileToken` — required only when `TURNSTILE_SECRET` is configured.

Response: `Content-Type: text/event-stream` (SSE). The Worker makes one streamed Claude call with
`web_search` (`max_uses: 5`, `max_tokens: 6000`) constrained to an **allow-list of authoritative
domains**, re-emits its own events to the browser (see [event shapes](#sse-event-shapes)), and on
completion persists the run + sources to D1. Per-IP (`20`) and global (`500`) daily caps apply.

Error responses are delivered **as an SSE `error` event** (the HTTP status is still `200` because
the stream has already opened), e.g. `{ "message": "That's a bit long (max 500 chars)…" }`.

### `GET /api/runs` / `GET /api/runs/:id`

```jsonc
// GET /api/runs
{ "runs": [ { "id": "uuid", "question": "…", "status": "done", "created_at": "…" } ] }

// GET /api/runs/:id  (404 { "error": "not found" } if unknown)
{ "run": { "id": "uuid", "question": "…", "status": "done", "report": "…markdown…", "model": "…" },
  "sources": [ { "url": "…", "title": "…", "snippet": "" } ] }
```

The stored `question` is **PII-redacted on write** (emails/SSNs/cards/phones masked before the D1
`INSERT`); the `report` is not redacted. See [data model](data-model.md#cloudflare-d1-live-edition).

### `DELETE /api/runs/:id`

Erases a run and its sources, returning `204 No Content` (idempotent — deleting an unknown id is also
`204`). No auth: the run id is an unguessable random UUID, so anonymous self-service deletion is
acceptable. This is the live edition's GDPR Art. 17 / CCPA right-to-delete control; a daily cron also
auto-purges runs older than 30 days. See [`compliance.md`](compliance.md).

## Production API (`apps/api`)

All application routes are under `/v1`; health routes are unprefixed. Auth is a Bearer JWT
obtained from `/v1/auth/login`. Sources:
[`auth/router.py`](../apps/api/src/atlas_api/auth/router.py),
[`runs/router.py`](../apps/api/src/atlas_api/runs/router.py),
[`health/router.py`](../apps/api/src/atlas_api/health/router.py).

### Health

| Method | Path | Response |
|---|---|---|
| GET | `/healthz` | `{ "status": "ok" }` |
| GET | `/readyz` | `{ "status": "ready" }` |
| GET | `/metrics` | Prometheus exposition (`text/plain; version=0.0.4`) |

`/metrics` is unprefixed and **unauthenticated** — RED request metrics plus run-lifecycle and
LLM-token counters, intended for in-cluster scraping (keep it off the public ingress). See
[observability §Metrics](observability.md#metrics-implemented).

### Auth

| Method | Path | Body | Success |
|---|---|---|---|
| POST | `/v1/auth/register` | `{ "email", "password" }` | `201` `{ "id", "email" }` (409 if duplicate) |
| POST | `/v1/auth/login` | `{ "email", "password" }` | `200` `{ "access_token", "refresh_token" }` (401 if bad) |
| POST | `/v1/auth/refresh` | `{ "refresh_token" }` | `200` new `{ "access_token", "refresh_token" }` |
| POST | `/v1/auth/logout` | — (Bearer access token) | `204`; revokes the access jti |

Tokens are JWTs (RFC 8725): algorithm allowlist, required `exp/iss/aud/sub/jti`, 600 s access TTL,
refresh rotation with reuse detection (a reused refresh revokes the whole token family). See
[`auth/tokens.py`](../apps/api/src/atlas_api/auth/tokens.py).

### Runs

All require `Authorization: Bearer <access_token>` and are scoped to the calling user.

| Method | Path | Body | Success | Notes |
|---|---|---|---|---|
| POST | `/v1/runs` | `{ "question", "data_types"? }` | `202` `RunOut` | enqueues the agent job (idempotent `_job_id=run:<id>`); honours `Idempotency-Key`; subject to quotas/kill-switch (`429`/`503`) |
| GET | `/v1/runs` | — | `200` `RunOut[]` | the caller's runs |
| GET | `/v1/runs/{id}` | — | `200` `RunDetailOut` | 404 if not owned/found |
| POST | `/v1/runs/{id}/cancel` | — | `202` | sets the Redis cancel flag |
| GET | `/v1/runs/{id}/events` | — (supports `Last-Event-ID`) | `200` `text/event-stream` | replay + live tail |

> **No `DELETE /v1/runs/{id}` yet.** The production edition has no self-service run-deletion endpoint;
> erasure relies on `ON DELETE CASCADE` from `users`. (The **live Worker** does expose
> `DELETE /api/runs/:id`.) A prod deletion endpoint + retention purge are planned — see
> [`compliance.md`](compliance.md).

#### `POST /v1/runs` request body & headers

```jsonc
// RunCreateIn
{ "question": "My SSN was in a healthcare breach. What now?",  // required, 3–500 chars
  "data_types": ["ssn", "medical"] }                            // optional, ≤ 16 entries, default []
```

- `data_types` — leaked-data categories; each maps to a curated **breach playbook** injected into the
  agent's writer node. Persisted on the run's `config` JSONB and read by the worker, so playbooks are
  now wired **end to end on the production path** (`schemas` → `repository` → `worker` → graph).
  Backward-compatible: omitting it behaves as before.
- `Idempotency-Key` (request header, optional) — a retried or double-clicked submission with the same
  key returns the **original** run instead of starting (and billing) a second one. The key dedupes for
  `idempotency_ttl_seconds` (default 24 h).

**Denial-of-wallet responses** ([`security/guardrails.py`](../apps/api/src/atlas_api/security/guardrails.py)):

| Status | When |
|---|---|
| `503` | Global kill-switch engaged (`service_paused`) — run submission paused by an operator |
| `429` | Daily quota exceeded — per-user (`daily_run_quota`, default 50) **or** per-IP (`daily_run_quota_ip`, default 200); counters reset at 00:00 UTC |

Both are returned as RFC-9457 problem responses. A run that exhausts the per-run token ceiling
(`max_run_tokens`) is not rejected but ends with `status: "truncated"` and a partial report.

Schemas ([`runs/schemas.py`](../apps/api/src/atlas_api/runs/schemas.py)):

```jsonc
// RunOut
{ "id": 1, "question": "…", "status": "queued", "created_at": "2026-06-29T…Z" }

// RunDetailOut (extends RunOut)
{ "id": 1, "question": "…", "status": "done", "created_at": "…",
  "report": "…markdown… | null",
  "sources": [ { "url": "…", "title": "… | null", "snippet": "… | null" } ] }
```

The stored/returned `question` is **PII-redacted on write** (masked before persistence). `status` is
one of the `run_status` values: `queued`, `planning`, `searching`, `verifying`, `writing`, `done`,
`cancelled`, `failed`, `truncated` ([`db/models.py`](../apps/api/src/atlas_api/db/models.py)).

### Consuming the production SSE stream

`EventSource` can't send an `Authorization` header, so the web client reads the SSE body from a
`fetch` stream and parses frames itself ([`apps/web/src/api.ts`](../apps/web/src/api.ts)). The
endpoint replays from `Last-Event-ID` (Redis `XREAD`) then tails live, emitting `: keepalive`
heartbeat comments (~every 15 s) and stopping after a terminal event.

## SSE event shapes

Both editions emit named SSE events (`event: <name>\ndata: <json>\n\n`). The production stream also
prefixes an `id:` (the Redis Stream entry id) used for `Last-Event-ID` reconnect.

### Production worker events ([`runs/streaming.py`](../apps/api/src/atlas_api/runs/streaming.py), [`worker.py`](../apps/api/src/atlas_api/worker.py))

| Event | Data | When |
|---|---|---|
| `status` | `{ "phase": "planning" \| "searching" \| "verifying" \| "writing" }` | on each graph phase |
| `plan` | `{ "subquestions": ["…"] }` | after the plan node |
| `source` | `{ "url", "title" }` | per newly-seen source (deduped by URL) |
| `report` | `{ "markdown": "…" }` | the finished cited report |
| `done` | `{ "id": <run_id>, "sources": <count> }` | terminal — success |
| `cancelled` | `{ "id": <run_id>, "sources": <count> }` | terminal — cancelled mid-run |
| `error` | `{ … }` | terminal — failure (in the terminal-events set) |

The production stream emits status/plan/source/report (not per-token). Terminal events are
`done` / `error` / `cancelled`.

### Live Worker events ([`apps/cloudflare/src/index.ts`](../apps/cloudflare/src/index.ts))

| Event | Data | When |
|---|---|---|
| `run` | `{ "id", "question" }` | run started |
| `status` | `{ "phase", "label" }` | triage → searching → verifying → writing |
| `agent` | `{ "agent": "searcher", "query"? }` | a web_search began / its query |
| `source` | `{ "url", "title", "snippet" }` | a web_search result (deduped) |
| `token` | `{ "delta": "…" }` | **per-token** report streaming (live edition only) |
| `done` | `{ "id", "sources": <count> }` | finished |
| `error` | `{ "message" }` | error (incl. model refusal) |

## Error format

The production API returns RFC-9457-style problem responses (no stack-trace leakage) via a global
handler ([`errors.py`](../apps/api/src/atlas_api/errors.py)); the web client reads the `title`
field. The live Worker returns `{ "error": "…" }` JSON for non-streaming routes and SSE `error`
events for the streaming route.
