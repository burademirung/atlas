# Atlas — Deep-Research Studio

> Ask a question → Atlas plans the research, **searches the live web**, grounds its
> answer in real sources, and **streams back a fully-cited Markdown report**.

Atlas is a multi-agent research studio. A user submits a research question; an agentic AI
panel decomposes it into sub-questions, fans out parallel web searches, tracks the sources
behind each claim, and streams a structured, cited report as it is written. Runs persist so
users can browse history and re-run.

The product is also the vehicle for demonstrating a complete, production-grade stack — every
required technology is **load-bearing, not decorative**. See [`STACK.md`](STACK.md) for the map.

> **New here?** Read [`AGENTS.md`](AGENTS.md) (the guide for AI agents and contributors:
> commands, conventions, guardrails) and browse the full [documentation index](docs/README.md).

**Status**

- Live edition — deployed: <https://atlas-research.burademirung.workers.dev>
- Production edition — runs locally via `docker compose up`; cloud deploy is code-complete (IaC + CI/CD), applied with your own AWS/Cloudflare credentials
- Tests — `uv run pytest` green; `ruff` + `mypy --strict` clean; CI gates on Trivy + gitleaks + CodeQL

---

## Two editions of the same product

Atlas ships in two editions that share one design but make opposite infrastructure trade-offs.

| | **Live (Cloudflare) edition** | **Production edition** |
|---|---|---|
| Where | [`apps/cloudflare/`](apps/cloudflare/) | [`apps/api/`](apps/api/) + [`apps/web/`](apps/web/) + [`infra/`](infra/) |
| Compute | One Cloudflare Worker (edge, zero servers) | FastAPI + arq workers on Kubernetes (AWS EKS) |
| Agent | Claude Opus 4.8 with the native `web_search` server tool | LangGraph `StateGraph`: plan → search ×N → verify → write, Claude via `langchain-anthropic`, Tavily search |
| Storage | Cloudflare D1 (SQLite) | PostgreSQL / RDS (7-table schema) |
| Streaming | SSE straight from the Worker | SSE backed by **Redis Streams** (replayable, `Last-Event-ID` reconnect) |
| Proves | Agentic AI + Cloudflare, end to end | FastAPI, PostgreSQL, Agentic AI, Kubernetes, AWS, Terraform, GitHub Actions |
| Deploy | `wrangler deploy` | `terraform apply` + `helm upgrade` via GitHub Actions |

The live edition is the "it really works" demo; the production edition is where the full stack
lives as code, ready for `terraform apply` + a push.

---

## Architecture overview

Both editions follow the same request flow: a browser submits a question, an agent plans and
searches the live web, and progress + the final cited report stream back over SSE.

```mermaid
flowchart TD
    user([User · React SPA]) -->|HTTPS POST /runs| edge

    subgraph live["Live edition (Cloudflare)"]
        cfw["Cloudflare Worker<br/>(SPA assets + research agent)"]
        d1[("D1<br/>runs · sources")]
        cfw -->|persist| d1
    end

    subgraph prod["Production edition (AWS EKS)"]
        edge["Cloudflare Worker<br/>(SPA assets + edge JWT + proxy)"]
        api["FastAPI API pods<br/>(routers → services → repos)"]
        pgb["PgBouncer"]
        pg[("PostgreSQL / RDS<br/>7 tables")]
        redis[("Redis / ElastiCache<br/>arq queue + per-run Streams")]
        worker["arq Agent Workers<br/>LangGraph + Claude"]
        edge -->|/v1/*| api
        api -->|read/write| pgb --> pg
        api -->|enqueue job| redis
        api -->|SSE: XREAD-tail stream| redis
        redis -->|KEDA scales on queue depth| worker
        worker -->|XADD step/token events| redis
        worker -->|persist run, sources, report| pgb
    end

    claude["Anthropic Claude API"]
    search["Web search<br/>(Tavily / native web_search)"]
    cfw --> claude
    cfw --> search
    worker --> claude
    worker --> search
```

The production streaming path is lossless on reconnect: workers `XADD` events to a per-run Redis
Stream; the SSE endpoint replays from `Last-Event-ID` (`XRANGE`) then tails live (`XREAD BLOCK`),
so any API pod can serve any client with no sticky sessions. See
[`docs/architecture.md`](docs/architecture.md) for C4 + sequence diagrams.

---

## The 7 required technologies — and where each lives

| # | Technology | Lives in | Role |
|---|---|---|---|
| 1 | **Python + FastAPI** | [`apps/api/`](apps/api/) | Async API, layered routers → services → repositories, Pydantic v2 |
| 2 | **PostgreSQL** | [`apps/api/src/atlas_api/db/models.py`](apps/api/src/atlas_api/db/models.py) | SQLAlchemy 2.0 async, 7-table schema, Alembic migration |
| 3 | **Agentic AI (LangGraph + Claude)** | [`apps/api/src/atlas_api/agents/`](apps/api/src/atlas_api/agents/), [`apps/cloudflare/src/index.ts`](apps/cloudflare/src/index.ts) | LangGraph `StateGraph` (parallel `Send` fan-out) + live Cloudflare Claude agent |
| 4 | **Terraform** | [`infra/terraform/`](infra/terraform/) | Modular AWS + Cloudflare; per-env state (`envs/{dev,prod}`) |
| 5 | **Kubernetes** | [`infra/k8s/atlas/`](infra/k8s/atlas/) | Helm chart: API + worker, KEDA autoscaling, migration hook, NetworkPolicies |
| 6 | **AWS** | [`infra/terraform/modules/`](infra/terraform/modules/) | EKS, RDS, ElastiCache, S3, ECR, IAM (Pod Identity), VPC |
| 7 | **GitHub Actions** | [`.github/workflows/`](.github/workflows/) | CI, CodeQL, CD (OIDC→AWS→ECR→Helm), Cloudflare deploy, Terraform plan |

Plus **Cloudflare** (Worker + D1 + native `web_search`) in [`apps/cloudflare/`](apps/cloudflare/).
Full evidence map: [`STACK.md`](STACK.md).

---

## Quickstart

### Production edition — `docker compose up`

One command brings up Postgres, Redis, PgBouncer, the API, the agent worker, and the web SPA.
Migrations run automatically (the `migrate` service runs `alembic upgrade head` before the API
and worker start).

```bash
# Provide an Anthropic key (and optionally a Tavily key) for real research runs.
# Without keys the worker falls back to a deterministic stub provider, so the
# full request → stream → report loop still works end to end for the demo.
export ANTHROPIC_API_KEY=sk-ant-...      # optional but recommended
export TAVILY_API_KEY=tvly-...           # optional (else stub search)

docker compose up --build
```

Then open:

- Web SPA — <http://localhost:8081>
- API (OpenAPI docs) — <http://localhost:8080/docs>

Default dev environment variables baked into `docker-compose.yml`:

| Variable | Dev value | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://atlas:atlas@pgbouncer:6432/atlas` | API/worker reach Postgres **through PgBouncer** |
| `REDIS_URL` | `redis://redis:6379/0` | arq queue + per-run Redis Streams |
| `JWT_SECRET` | `dev-secret-change-me-32-chars-min!` | replace in any real deployment |
| `ANTHROPIC_API_KEY` | from your shell | enables real Claude calls |
| `TAVILY_API_KEY` | from your shell | enables real web search |
| `RESEARCH_MODEL` | `claude-opus-4-8` | model used by the agent graph |

### Live (Cloudflare) edition — `wrangler dev`

```bash
cd apps/cloudflare
npm install
npx wrangler secret put ANTHROPIC_API_KEY   # for `wrangler deploy`; for local use a .dev.vars file
npx wrangler d1 migrations apply atlas-research --local
npx wrangler dev
```

`wrangler dev` serves the SPA from `public/` and the research API from `src/index.ts`. Deploy to
the edge with `npx wrangler deploy`.

---

## Repository layout

```
.
├── apps/
│   ├── api/                 FastAPI service, LangGraph agents, arq worker, Alembic
│   │   ├── src/atlas_api/
│   │   │   ├── agents/      LangGraph graph, nodes, providers, runner
│   │   │   ├── auth/        JWT (RFC 8725), argon2id passwords
│   │   │   ├── db/          SQLAlchemy 2.0 models + async engine
│   │   │   ├── runs/        run router, repository, Redis-Stream SSE
│   │   │   ├── evals/       agent-quality eval harness
│   │   │   ├── migrations/  Alembic
│   │   │   └── worker.py    arq WorkerSettings
│   │   └── tests/           pytest (+ testcontainers)
│   ├── cloudflare/          Live Worker: Claude + native web_search + D1 + SPA
│   │   ├── src/index.ts     the Worker (research agent + SSE + persistence)
│   │   ├── public/          static SPA assets
│   │   └── migrations/      D1 SQL
│   └── web/                 React + Vite SPA (containerized origin for prod edition)
├── infra/
│   ├── terraform/           modules/ + envs/{dev,prod} (separate state per env)
│   ├── k8s/atlas/           Helm chart (KEDA, migration hook, NetworkPolicies, PSS)
│   └── local/pgbouncer/     local PgBouncer config for docker compose
├── .github/workflows/       ci · codeql · cd · pages (Cloudflare) · terraform · eval
├── docs/                    architecture · runbook · threat-model · cost-notes · adr/
├── docker-compose.yml       full production-edition stack, locally
└── STACK.md                 the required-tech map
```

---

## Testing

```bash
# Backend: ruff + mypy + pytest (testcontainers spin up throwaway Postgres/Redis).
cd apps/api
uv sync --all-groups
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest

# Cloudflare Worker / SPA: type-check.
cd apps/cloudflare && npm ci && npx tsc --noEmit

# Web SPA: production build.
cd apps/web && npm ci && npm run build
```

The agent-quality eval (groundedness / no-uncited-claims / source diversity) runs weekly and on
demand via [`.github/workflows/eval.yml`](.github/workflows/eval.yml); a fast structural version
runs per-PR via `tests/test_evals.py`.

---

## Documentation

The full map is the [documentation index](docs/README.md) (organized by the
[Diátaxis](https://diataxis.fr/) framework). Quick links, grouped:

**Getting started**

- [`AGENTS.md`](AGENTS.md) — commands, conventions, and guardrails for AI agents & contributors
- [`docs/development.md`](docs/development.md) — local dev setup (API, worker, Worker, web, compose)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — set up, branch, commit, test, open a PR

**Architecture & design**

- [`docs/architecture.md`](docs/architecture.md) — C4 context + container views, request sequence, data model
- [`docs/agent-design.md`](docs/agent-design.md) — the LangGraph graph, fan-out, verify, spotlighting, playbooks, MCP, evals
- [`docs/data-model.md`](docs/data-model.md) — the Postgres 7-table schema and the Cloudflare D1 schema
- [`docs/api-reference.md`](docs/api-reference.md) — the Worker `/api/*` and FastAPI `/v1/*` surfaces + SSE events
- [`STACK.md`](STACK.md) — where each required technology lives, with evidence

**Operations**

- [`docs/deployment.md`](docs/deployment.md) — how each edition deploys (wrangler, Terraform, Helm, CI/CD)
- [`docs/runbook.md`](docs/runbook.md) — deploy, secrets/env, migrations, rollback, eval, failure modes
- [`docs/testing.md`](docs/testing.md) — pytest + testcontainers, Vitest, deterministic agent tests, evals
- [`docs/observability.md`](docs/observability.md) — logging, metrics, tracing (implemented vs planned)
- [`docs/cost-notes.md`](docs/cost-notes.md) — cost model for both editions + how to keep dev cheap

**Security**

- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure policy + posture summary
- [`docs/security.md`](docs/security.md) — defense-in-depth security architecture (OWASP/NIST mapped)
- [`docs/threat-model.md`](docs/threat-model.md) — attack paths + mitigations (prompt injection, denial-of-wallet, XSS, SSRF, authn/z, secrets, PII)

**Decisions (ADRs)** — [`docs/adr/`](docs/adr/)

- [`0001-cloudflare-vs-aws-editions.md`](docs/adr/0001-cloudflare-vs-aws-editions.md) — why two editions (live Cloudflare vs production AWS)
- [`0002-langgraph-multi-agent.md`](docs/adr/0002-langgraph-multi-agent.md) — why a LangGraph multi-agent graph
- [`0003-sse-redis-streams-not-pubsub.md`](docs/adr/0003-sse-redis-streams-not-pubsub.md) — why Redis Streams (not Pub/Sub) behind SSE
- [`0004-keda-for-queue-autoscaling.md`](docs/adr/0004-keda-for-queue-autoscaling.md) — why KEDA for queue-driven autoscaling
- [`0005-terraform-per-env-state.md`](docs/adr/0005-terraform-per-env-state.md) — why per-environment Terraform state

**Component guides** (per-directory READMEs)

- [`apps/api/README.md`](apps/api/README.md) — the FastAPI service, LangGraph agents, and arq worker
- [`infra/terraform/README.md`](infra/terraform/README.md) — the Terraform root + modules
- [`infra/k8s/README.md`](infra/k8s/README.md) — the Kubernetes manifests overview
- [`infra/k8s/atlas/README.md`](infra/k8s/atlas/README.md) — the Atlas Helm chart
- [`.github/README.md`](.github/README.md) — the CI/CD workflows

**Project meta**

- [`README.md`](README.md) — this file · [`docs/README.md`](docs/README.md) — the documentation index
- [`CHANGELOG.md`](CHANGELOG.md) — release history (Keep a Changelog)
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant
- [`docs/documentation-strategy.md`](docs/documentation-strategy.md) — what docs this class of project needs, and why
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — the full design spec behind Atlas
