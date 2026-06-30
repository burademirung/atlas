# Development Setup

> Run Firstline / Atlas locally — the backend, the agent worker, the live Worker, the web SPA, and
> the full `docker compose` stack. All commands and paths below are real; verify with the repo.

## Table of contents

- [Prerequisites](#prerequisites)
- [The fast path: the full stack with Docker Compose](#the-fast-path-the-full-stack-with-docker-compose)
- [Backend (`apps/api`) by hand](#backend-appsapi-by-hand)
- [Live Worker (`apps/cloudflare`)](#live-worker-appscloudflare)
- [Web SPA (`apps/web`)](#web-spa-appsweb)
- [The MCP server](#the-mcp-server)
- [Environment variables](#environment-variables)
- [Test / lint / type commands](#test--lint--type-commands)

## Prerequisites

| Tool | Version | For |
|---|---|---|
| Python | 3.12 (`==3.12.*`) | `apps/api` |
| [uv](https://docs.astral.sh/uv/) | recent | Python dependency + task runner |
| Node.js | LTS | `apps/cloudflare`, `apps/web` |
| Docker + Compose | recent | the full local stack |
| Terraform | ≥ 1.10 | `infra/terraform` (optional, deploy only) |
| Helm | 3.x | `infra/k8s` (optional, deploy only) |

Provider keys are **optional** for local dev: without `ANTHROPIC_API_KEY` / `TAVILY_API_KEY` the
worker falls back to a deterministic **stub** search provider, so the full request → stream →
report loop still runs offline. (Real `plan`/`verify`/`write` calls do need an Anthropic key.)

## The fast path: the full stack with Docker Compose

One command brings up Postgres, Redis, PgBouncer, the API, the agent worker, and the web SPA.
Migrations run automatically — the `migrate` service runs `alembic upgrade head` before the API
and worker start.

```bash
# Optional, for real research runs:
export ANTHROPIC_API_KEY=sk-ant-...
export TAVILY_API_KEY=tvly-...

docker compose up --build
```

Then open:

- Web SPA — <http://localhost:8081>
- API (OpenAPI docs) — <http://localhost:8080/docs>

Services and ports (from [`docker-compose.yml`](../docker-compose.yml)):

| Service | Image / build | Port | Notes |
|---|---|---|---|
| `db` | `postgres:16-alpine` | 5432 | user/pass/db all `atlas` |
| `redis` | `redis:7-alpine` | 6379 | arq queue + per-run Streams |
| `pgbouncer` | `edoburu/pgbouncer` | 6432 | the API/worker reach Postgres **through** this |
| `migrate` | `apps/api` | — | one-shot `alembic upgrade head` |
| `api` | `apps/api` | 8080 | FastAPI / uvicorn |
| `worker` | `apps/api` | — | `arq atlas_api.worker.WorkerSettings` |
| `web` | `apps/web` | 8081 → 80 | nginx serving the SPA, proxying `/v1` |

## Backend (`apps/api`) by hand

```bash
cd apps/api
uv sync --all-groups                          # install runtime + dev deps

# Run the API (needs a reachable Postgres + Redis — e.g. from docker compose):
uv run uvicorn atlas_api.main:app --reload --port 8080

# Run the agent worker (consumes the arq queue, runs the LangGraph graph):
uv run arq atlas_api.worker.WorkerSettings

# Migrations:
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

The app factory is `atlas_api.main:create_app`; `atlas_api.main:app` is the module-level instance
uvicorn serves. Settings are read at startup via `pydantic-settings`
([`config.py`](../apps/api/src/atlas_api/config.py)), so the required env vars below must be set.

## Live Worker (`apps/cloudflare`)

```bash
cd apps/cloudflare
npm install
npx wrangler d1 migrations apply atlas-research --local   # apply D1 schema locally
npx wrangler dev                                          # serves SPA (public/) + /api/* (src/index.ts)
```

For the Worker to make real Claude calls locally, provide `ANTHROPIC_API_KEY` via a `.dev.vars`
file (git-ignored). For deploys, use `npx wrangler secret put ANTHROPIC_API_KEY`. The Worker calls
the Anthropic Messages API directly (`api.anthropic.com`) with that key; note the `AI` (Workers AI)
binding is declared in [`wrangler.jsonc`](../apps/cloudflare/wrangler.jsonc) but the research path
uses the Anthropic API key, not Workers AI.

npm scripts (from `package.json`): `dev` (`wrangler dev --remote`), `deploy`, `typecheck`
(`tsc --noEmit`), `test` (`vitest`), `db:migrate` (`wrangler d1 migrations apply atlas-research --remote`).

## Web SPA (`apps/web`)

```bash
cd apps/web
npm ci
npm run dev        # Vite dev server (see vite.config.ts for the dev proxy to /v1)
npm run build      # production build (tsc + vite build) — what CI checks
```

The SPA points at the API via `VITE_API_BASE` (defaults to same-origin); in `docker compose` the
nginx container proxies `/v1` to the API. SSE is consumed with a fetch stream (not `EventSource`)
so it can send the `Authorization` header — see [`apps/web/src/api.ts`](../apps/web/src/api.ts).

## The MCP server

The Firstline MCP server exposes breach-response tools over stdio for any MCP client
([`mcp_server.py`](../apps/api/src/atlas_api/mcp_server.py)):

```bash
cd apps/api
uv run firstline-mcp        # console script defined in pyproject.toml
# or: uv run python -m atlas_api.mcp_server
```

Tools: `list_data_types`, `recovery_steps`, `breach_notification_law`, `pwned_password`
(free, k-anonymity), `check_email_breaches` (needs `HIBP_API_KEY`). See
[`docs/agent-design.md`](agent-design.md#mcp-server).

## Environment variables

Baseline from [`.env.example`](../.env.example) (consumed by `pydantic-settings`):

| Var | Required | Default / example | Purpose |
|---|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://atlas:atlas@pgbouncer:6432/atlas` | DB DSN — **always via PgBouncer** |
| `REDIS_URL` | ✅ | `redis://redis:6379/0` | arq queue + per-run Streams + JWT jti store |
| `JWT_SECRET` | ✅ | `dev-secret-change-me-32-chars-min!` | HS256 signing secret (≥ 32 chars) |
| `ENVIRONMENT` | optional | `dev` | `dev` / `production` |
| `ANTHROPIC_API_KEY` | for real runs | — | Claude API |
| `TAVILY_API_KEY` | optional | — | live web search (else stub) |
| `RESEARCH_MODEL` | optional | `claude-opus-4-8` | model used by the graph |

JWT knobs (`JWT_ISSUER=atlas`, `JWT_AUDIENCE=atlas-api`, `JWT_ALGORITHM=HS256`,
`ACCESS_TTL_SECONDS=600`, `REFRESH_TTL_SECONDS=1209600`), argon2 params
(`ARGON2_MEMORY_KIB=19456`, `ARGON2_TIME_COST=2`, `ARGON2_PARALLELISM=1`), and agent caps
(`MAX_SUBQUESTIONS=4`, `MAX_SOURCES_PER_Q=3`) all have safe defaults in `config.py`.

## Test / lint / type commands

```bash
# Backend — what CI runs (ci.yml):
cd apps/api
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest                       # testcontainers spin up throwaway Postgres/Redis

# Live Worker:
cd apps/cloudflare && npm run typecheck && npm test

# Web SPA:
cd apps/web && npm run build

# Infra:
cd infra/terraform/envs/dev && terraform fmt -check && terraform validate
helm template atlas infra/k8s/atlas -n atlas | head
```

More detail in [`docs/testing.md`](testing.md).
</content>
