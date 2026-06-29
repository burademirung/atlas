# Deep-Research Studio (Atlas) — Design Spec

**Status:** Approved (2026-06-29)
**Codename:** Atlas (rename freely)
**Owner:** vlad@degenito.ai

---

## 1. Summary

Atlas is a multi-tenant web application where a user submits a research question and an
**agentic AI panel** decomposes it, fans out parallel web searches, **cross-checks and verifies**
claims against real sources, and **streams** back a structured, fully-cited report. Runs persist;
users browse history, re-run, cancel in-flight runs, and export reports (Markdown / PDF).

The product is the vehicle for demonstrating a complete, production-grade stack:
**Python + FastAPI, PostgreSQL, Agentic AI (LangGraph + Claude), Kubernetes, AWS, Terraform,
GitHub Actions, and Cloudflare.** Every required technology is load-bearing, not decorative.

### Non-goals (v1)
- No fine-tuning or self-hosted models (Claude via Anthropic API).
- No team/org RBAC beyond per-user isolation.
- No billing/payments (cost *guardrails* yes; monetization no).
- No mobile app (responsive web only).

---

## 2. Locked decisions

| Decision | Choice | Notes |
|---|---|---|
| Product | Deep-Research Studio | Multi-agent cited research with streaming UI |
| Search backend | **Tavily (default)** | Search+extract gives the verifier raw page text. Adapters: Anthropic `web_search`, Exa |
| Streaming | **SSE** | Cloudflare-friendly; relayed via Redis pub/sub (multi-pod safe) |
| Queue / workers | **Redis + arq** | Async workers, HPA on queue depth |
| K8s packaging | **Helm** | Single chart, env values files |
| Auth | **App-level JWT** (access + refresh) | Cloudflare Access optional later |
| Deploy ownership | User applies with own AWS/Cloudflare creds | We deliver runnable code + complete IaC |

---

## 3. Architecture

```
Browser (React SPA on Cloudflare Pages)
   │  HTTPS + SSE
   ▼
Cloudflare Worker (edge: auth check, rate-limit, proxy to API)
   │
   ▼
FastAPI (EKS pods)  ──writes──►  PostgreSQL / RDS
   │  enqueue job                      ▲
   ▼                                    │ progress + results
Redis / ElastiCache (arq queue + pub/sub) ──► Agent Workers (EKS pods)
                                          │  LangGraph graph + Claude
                                          ├─► Search provider (Tavily / Anthropic / Exa)
                                          └─► S3 (report exports: PDF / MD)
```

- **Streaming path:** workers publish step events to a per-run **Redis pub/sub** channel; the
  FastAPI SSE endpoint subscribes and relays to the browser. Because state lives in Redis, any
  API pod can serve any client (no sticky sessions).
- **Why workers + queue (K8s justification):** research runs take minutes and fan out; the API
  Deployment and worker Deployment scale independently, worker HPA keys off queue depth.

---

## 4. Agent graph (LangGraph + Claude)

```
plan ─► [search ×N parallel] ─► dedupe/rank ─► verify (claim↔source) ─► write ─► critic ─► (gaps & budget left? loop : done)
```

| Node | Model | Responsibility |
|---|---|---|
| Planner | Claude Opus | Decompose question → bounded set of sub-questions |
| Searcher ×N | Claude Sonnet | Query Tavily, read extracted content, summarize per sub-question (parallel) |
| Dedupe/rank | — (code) | Dedup sources by URL hash, rank by relevance |
| Verifier | Claude Sonnet | Each claim must cite ≥1 source or is dropped/flagged |
| Writer | Claude Opus | Stream the cited report (token streaming) |
| Critic | Claude Sonnet | "What's missing?" → at most one bounded re-loop |

- **Search provider is pluggable** behind a `SearchProvider` interface (`search()`, `extract()`).
  Default Tavily; Anthropic `web_search` and Exa adapters included.
- **No uncited assertions:** every claim row carries `source_ids[]`. The writer is constrained to
  the verified claim set.
- Exact model IDs and tool-use wiring confirmed against the current Claude API reference before
  coding (do not hardcode from memory).

---

## 5. Cost & abuse guardrails (first-class requirement)

- **Per-run caps:** max sub-questions, max sources, max critic loops, hard **token budget**.
- **Per-user daily quota:** N runs / day; rejects with 429 + clear message.
- **Budget kill-switch:** when a run exceeds its token budget, it ends cleanly with a
  partial report marked `truncated`, never silently spins.
- All caps are config (env / Helm values), enforced in the worker between graph nodes.

---

## 6. Run lifecycle & cancellation

States: `queued → planning → searching → verifying → writing → done` (or `cancelled` / `failed` / `truncated`).
- `POST /runs/{id}/cancel` sets a cancel flag in Redis; the worker checks it between nodes and
  exits cooperatively, persisting a partial report.

---

## 7. Data model (PostgreSQL, SQLAlchemy + Alembic)

| Table | Key columns |
|---|---|
| `users` | id, email, password_hash (argon2), created_at |
| `research_runs` | id, user_id, question, status, config(jsonb), verdict, tokens_used, created_at |
| `run_steps` | id, run_id, agent, phase, status, tokens, latency_ms, payload(jsonb) — powers live tree + observability |
| `sources` | id, run_id, url, url_hash, title, snippet, content_excerpt |
| `claims` | id, run_id, text, source_ids(int[]), confidence |
| `reports` | id, run_id, markdown, export_s3_key, truncated(bool) |

- In-run dedup by `url_hash`. **`pgvector` cross-run source cache → Phase 2 (deferred, YAGNI for v1).**

---

## 8. Backend (FastAPI)

- Async, layered: **routers → services → repositories**. Pydantic v2 schemas.
- Endpoints: auth (`/auth/register`, `/auth/login`, `/auth/refresh`), `POST /runs`,
  `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` (SSE), `POST /runs/{id}/cancel`,
  `POST /runs/{id}/export`.
- Cross-cutting: structured JSON logging, OpenTelemetry traces, Prometheus `/metrics`,
  `/healthz` + `/readyz`, request-id middleware, global error handler.

---

## 9. Frontend (premium GUI — Cloudflare Pages)

React + TypeScript + Vite + Tailwind + shadcn/ui. Screens:
- **New Research** — question + depth slider (maps to caps).
- **Live Run** — animated agent tree, token-streaming report, source cards appearing as found.
- **Report** — cited, collapsible sections, export buttons.
- **History / Dashboard** — past runs, status, re-run.

Aesthetic: dark, editorial, "research instrument" — built with the frontend-design skill so it
does not read as a template.

---

## 10. Infrastructure & ops (stack-as-code)

- **Docker:** multi-stage images for `api`, `worker`, `web` (non-root, read-only FS, minimal base).
- **docker-compose:** one command → full app live locally (postgres, redis, api, worker, web).
  **This is the "real demo."**
- **Terraform (modular):** `network` (VPC), `eks`, `rds` (Postgres), `elasticache` (Redis),
  `s3`, `ecr`, `iam/irsa`, `secrets`, `cloudflare` (Pages + Worker + DNS). Remote state on
  S3 + DynamoDB lock. Dev/prod via workspaces. Cost-conscious default sizing.
- **Kubernetes (Helm):** api Deployment, worker Deployment, HPA (queue depth), Services,
  Ingress (ALB), External Secrets, Alembic migration Job, NetworkPolicies, PDBs.
- **GitHub Actions:**
  - `ci.yml` — ruff + mypy + pytest + coverage; web lint/build; Trivy image scan.
  - `cd.yml` — build/push ECR → `helm upgrade` on EKS.
  - `pages.yml` — deploy web to Cloudflare Pages.
  - `terraform.yml` — fmt/validate/plan on PR, gated apply on main.
- **Observability:** structured logs + Prometheus metrics + OTel traces → CloudWatch.
  (No self-hosted Grafana/Tempo in v1 — YAGNI.)

---

## 11. Security

- JWT access + refresh; argon2 password hashing.
- Per-user run isolation enforced at the repository layer.
- Secrets via AWS Secrets Manager + External Secrets — never baked into images or git.
- Cloudflare rate-limit + WAF at the edge; app-level per-user quotas.
- Containers: non-root, read-only root FS, dropped capabilities, Trivy gate in CI.
- Least-privilege IRSA per workload (S3, Secrets Manager).
- Threat model documented in M4.

---

## 12. Testing

- **Backend:** pytest + pytest-asyncio; API tests via `httpx` against a throwaway Postgres
  (testcontainers). **Agents tested with mocked LLM + mocked search** for determinism; a couple
  of live "smoke" tests gated behind a flag/secret.
- **Frontend:** Vitest unit + Playwright e2e against the local compose stack.
- **Coverage gate** enforced in CI.

---

## 13. Repository layout

```
atlas/
  apps/api/         FastAPI app, agent graph, alembic migrations
  apps/web/         React + Vite SPA
  infra/terraform/  modules + envs (dev/prod)
  infra/k8s/        Helm chart
  infra/cloudflare/ Worker source
  .github/workflows/
  docs/             architecture (C4 + sequence), ADRs, runbooks, threat model, cost notes
  docker-compose.yml
  README.md         premium: architecture diagram + quickstart + tech map
```

---

## 14. Milestones (sequenced; each independently valuable)

| Milestone | Delivers | Definition of done |
|---|---|---|
| **M1 — Working product (local)** | FastAPI + Postgres + LangGraph agents + SSE + React via docker-compose; cost guardrails; cancellation | `docker compose up` → submit question → watch agent tree → get cited report; mocked-LLM tests green |
| **M2 — Productionize** | Hardened images, Helm chart, GitHub Actions CI | Green CI, deployable artifacts, Trivy clean |
| **M3 — Cloud** | Terraform (VPC/EKS/RDS/ElastiCache/S3/ECR/IAM) + Cloudflare Pages+Worker + CD pipelines | `terraform apply` + push → live on user's accounts |
| **M4 — Docs** | C4 + sequence diagrams, ADRs, runbooks, threat model, cost notes, "how each required tech is used" map | Comprehensive docs deliverable complete |

The full required stack (FastAPI, Postgres, Agentic AI, K8s, AWS, Terraform, GitHub Actions,
Cloudflare) is covered across M1–M4; nothing is cut, only sequenced.

---

## 15. Open items to confirm before/at coding time

- Exact Claude model IDs + tool-use schema (verify against current Claude API reference).
- Tavily/Anthropic/Exa API key provisioning (user supplies at deploy).
- Final cap values (defaults proposed; tune after first live runs).
