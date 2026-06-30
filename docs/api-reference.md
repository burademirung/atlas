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
| POST | `/v1/runs` | `{ "question" }` (3–500 chars) | `202` `RunOut` | enqueues the agent job (idempotent `_job_id=run:<id>`) |
| GET | `/v1/runs` | — | `200` `RunOut[]` | the caller's runs |
| GET | `/v1/runs/{id}` | — | `200` `RunDetailOut` | 404 if not owned/found |
| POST | `/v1/runs/{id}/cancel` | — | `202` | sets the Redis cancel flag |
| GET | `/v1/runs/{id}/events` | — (supports `Last-Event-ID`) | `200` `text/event-stream` | replay + live tail |

Schemas ([`runs/schemas.py`](../apps/api/src/atlas_api/runs/schemas.py)):

```jsonc
// RunOut
{ "id": 1, "question": "…", "status": "queued", "created_at": "2026-06-29T…Z" }

// RunDetailOut (extends RunOut)
{ "id": 1, "question": "…", "status": "done", "created_at": "…",
  "report": "…markdown… | null",
  "sources": [ { "url": "…", "title": "… | null", "snippet": "… | null" } ] }
```

`status` is one of the `run_status` values: `queued`, `planning`, `searching`, `verifying`,
`writing`, `done`, `cancelled`, `failed`, `truncated`
([`db/models.py`](../apps/api/src/atlas_api/db/models.py)).

> **Note (honest):** `POST /v1/runs` accepts only `question` today — there is no `data_types` field
> on the production request schema, and the arq worker invokes the graph without `data_types`, so
> the breach playbooks are not injected on the production run path yet (they *are* wired into the
> agent's `write_node`, the runner, and the MCP server). See
> [agent design](agent-design.md#breach-playbooks-as-a-context-layer).

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
</content>
