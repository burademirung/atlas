# Deep-Research Studio (Atlas) — Design Spec

**Status:** Approved, revised v2 after deep multi-domain review (2026-06-29)
**Codename:** Atlas (rename freely)
**Owner:** vlad@degenito.ai

> v2 incorporates a five-domain adversarial review (agentic-AI, backend, infra, security, CI/CD)
> against current published standards. Changes are flagged inline as **[v2]**. The most
> consequential: queue-depth autoscaling requires **KEDA** (plain HPA cannot do it); the two
> agentic-specific security risks — **indirect prompt injection** and **SSRF→IMDS** — are now
> first-class controls; streaming uses **Redis Streams** (replayable) not pub/sub.

---

## 1. Summary

Atlas is a multi-tenant web application where a user submits a research question and an
**agentic AI panel** decomposes it, fans out parallel web searches, **verifies claims by
entailment** against real sources, and **streams** back a structured, fully-cited report. Runs
persist; users browse history, re-run, cancel in-flight runs, and export (Markdown / PDF).

The product is the vehicle for demonstrating a complete, production-grade stack:
**Python + FastAPI, PostgreSQL, Agentic AI (LangGraph + Claude), Kubernetes, AWS, Terraform,
GitHub Actions, Cloudflare.** Every required technology is load-bearing, not decorative.

### Non-goals (v1)
- No fine-tuning / self-hosted models (Claude via Anthropic API).
- No team/org RBAC beyond per-user isolation.
- No billing/payments (cost *guardrails* yes; monetization no).
- No mobile app (responsive web only).

---

## 2. Locked decisions

| Decision | Choice | Notes |
|---|---|---|
| Product | Deep-Research Studio | Multi-agent cited research with streaming UI |
| Search backend | **Tavily (default)** | search+extract returns raw page text for entailment checks. **[v2]** Anthropic adapter must pair `web_search` + `web_fetch` and degrades grounding fidelity; Exa `/contents` is the other adapter |
| Streaming transport | **SSE** | Cloudflare-friendly |
| Streaming backbone | **[v2] Redis Streams** | Replayable per-run log (`XADD`/`XREAD`), `Last-Event-ID` reconnect; pub/sub is lossy and was rejected |
| Queue / workers | **Redis + arq** | `allow_abort_jobs`, `_job_id` idempotency |
| Worker autoscaling | **[v2] KEDA (Redis scaler)** | Queue-depth + scale-to-zero. Plain HPA/metrics-server **cannot** read queue depth — this was a correctness gap |
| K8s packaging | **Helm** | Single chart; Argo CD deferred (ADR) |
| Workload identity | **[v2] EKS Pod Identity** | Recommended over IRSA for greenfield EKS; IRSA documented fallback |
| TF state locking | **[v2] S3 native (`use_lockfile`)** | DynamoDB lock is deprecated |
| Environments | **[v2] separate root config + state per env** | `envs/{dev,prod}`; workspaces-for-environments is an anti-pattern |
| Frontend hosting | **[v2] Cloudflare Worker + static assets** | Pages is in maintenance mode; one Worker serves SPA + edge auth/proxy |
| Auth | **App-level JWT** (RFC 8725) | Cloudflare Access optional later |
| Deploy ownership | User applies with own AWS/Cloudflare creds | We deliver runnable code + complete IaC |

---

## 3. Architecture

```
Browser (React SPA)
   │  HTTPS + SSE
   ▼
Cloudflare Worker  (serves SPA static assets + edge auth (full JWT verify) + rate-limit + proxy)
   │  must STREAM, not buffer, the SSE route
   ▼
FastAPI (EKS pods)  ──writes──►  PgBouncer ──► PostgreSQL / RDS
   │  enqueue (arq, _job_id)                         ▲
   ▼                                                  │ replay run_steps on reconnect
Redis / ElastiCache  ── arq queue + per-run Redis Stream ──► Agent Workers (EKS pods)
   │  KEDA scales workers on list/stream depth          │  LangGraph + Claude (checkpointer in Postgres)
   │                                                     ├─► Search provider (Tavily / Anthropic / Exa)
   └─ SSE endpoint XREAD-tails the stream                └─► S3 (report exports, pre-signed)
```

- **[v2] Streaming path:** workers `XADD` step/token events to a per-run **Redis Stream**; the SSE
  endpoint replays from `Last-Event-ID` (`XRANGE`) then tails live (`XREAD BLOCK`). Reconnects are
  lossless within retention; older gaps replay from persisted `run_steps`. Any API pod serves any
  client (no sticky sessions). Token streaming sourced from LangGraph `astream_events`.
- **[v2] Why KEDA + workers (K8s justification):** runs take minutes and fan out; the API
  Deployment (CPU HPA) and worker Deployment (**KEDA ScaledObject** on Redis depth, scale-to-zero)
  scale independently.

---

## 4. Agent graph (LangGraph + Claude)

```
plan ─► [search ×N via Send API] ─► dedupe/rank ─► verify (entailment) ─► write ─► critic ─► (gaps & budget? loop : done)
```

| Node | Model **[v2]** | Responsibility |
|---|---|---|
| Planner | `claude-opus-4-8` | Decompose → bounded sub-questions (**structured output**) |
| Searcher ×N | `claude-sonnet-4-6` | Query provider, read extracted content, summarize (parallel) |
| Dedupe/rank | `claude-haiku-4-5` / code | Dedup by URL hash, rank |
| Verifier | `claude-sonnet-4-6` | **Entailment**: cited source text must *support* the claim (not mere presence) — **structured output**, native Citations |
| Writer | `claude-opus-4-8` | Stream cited report (token streaming) |
| Critic | `claude-sonnet-4-6` | "What's missing?" → ≤1 bounded re-loop (hard-capped server-side) |

**[v2] Claude API specifics (verify against current docs before coding — do not code from memory):**
- Model IDs above; **no date suffixes**.
- Thinking via `thinking:{type:"adaptive"}` + `output_config:{effort:...}`. On Opus 4.8/4.7 & Sonnet 4.6
  the old `thinking.budget_tokens` returns 400, and `temperature`/`top_p`/assistant-prefill are rejected.
- **Anthropic `web_search` returns cited summaries, not raw page text** — pair with `web_fetch` for
  grounding; `web_fetch` only fetches URLs already in-conversation and is unavailable on Bedrock/Vertex.
  This is why Tavily is the default.
- **Grounding:** planner/verifier use **structured outputs** (`output_config.format` / strict tool use);
  the writer emits **native Citations** (`citations:{enabled:true}` on `document` blocks) for char-level
  cited spans. No uncited assertions; injected source text cannot self-certify (see §11.1).

**[v2] Fan-out & resilience:**
- Parallel search via LangGraph **`Send` API** (dynamic map-reduce), bounded by `max_concurrency`.
- **A LangGraph superstep is atomic** — one branch raising aborts all siblings. Each searcher node
  **catches its own errors** and returns a degraded-result sentinel; per-node retry policy.
- **Durable execution:** LangGraph **Postgres checkpointer** (`AsyncPostgresSaver`) gives crash-resume,
  cooperative cancel, and `interrupt()` for optional human-in-the-loop plan approval.

---

## 5. Cost & abuse guardrails (first-class)

- **Per-run caps:** max sub-questions, max sources, max critic loops (server-enforced), hard **token budget**.
- **[v2] Model-aware budgeting:** `task_budget` (countdown so the model self-wraps) + **prompt caching**
  (`cache_control`) on the shared source context reused across verifier/writer/critic (~90% cheaper prefix).
- **[v2] Atomic enforcement:** per-user daily run quota + token budget enforced with a **single Redis Lua
  `EVAL`** (check-and-increment) or Postgres `UPDATE … WHERE used < limit RETURNING` — never read-then-write
  (TOCTOU). Per-run token budget checked in-worker between nodes (single owner, no race).
- **[v2] Denial-of-wallet (LLM10):** **global/tenant daily spend kill-switch**; **per-provider cost meters**
  (LLM *and* Tavily) with alerting; registration behind **Cloudflare Turnstile**. Budget-kill yields a
  `truncated` partial report, never a silent spin.

---

## 6. Run lifecycle & cancellation

States: `queued → planning → searching → verifying → writing → done` (or `cancelled`/`failed`/`truncated`).
- **[v2]** Cancellation via arq `allow_abort_jobs=True` + `job.abort()`; worker also traps **SIGTERM**
  (rollout/scale-down) and checkpoints a partial report at the between-node boundary. Same path serves
  cancel, budget-kill, and graceful shutdown.

---

## 7. Data model (PostgreSQL, SQLAlchemy 2.0 async + Alembic)

| Table | Key columns |
|---|---|
| `users` | id, **email citext UNIQUE**, password_hash (argon2id), created_at |
| `research_runs` | id, user_id→users **ON DELETE CASCADE**, question, status, config(jsonb), verdict, tokens_used, created_at |
| `run_steps` | id, run_id→runs CASCADE, agent, phase, status, tokens, latency_ms, payload(jsonb) — live tree + telemetry; also the SSE replay source |
| `sources` | id, run_id CASCADE, url, url_hash, title, snippet, content_excerpt — **UNIQUE(run_id, url_hash)** |
| `claims` | id, run_id CASCADE, text, confidence |
| **`claim_sources` [v2]** | claim_id→claims, source_id→sources, **PK(claim_id, source_id)**, FKs CASCADE — replaces `source_ids int[]` (FK integrity + clean "claims citing source X" query) |
| `reports` | id, run_id CASCADE, markdown, export_s3_key, truncated(bool) |

- **[v2] Indexes:** `research_runs(user_id, created_at desc)`, `run_steps(run_id)`, `sources(run_id)`,
  `claims(run_id)`, `reports(run_id)`; unique `sources(run_id, url_hash)` enforces in-run dedup in the DB.
- **[v2] Multi-tenancy defense-in-depth:** repository-layer `user_id` filter **plus** Postgres **RLS**
  (policy on `app.user_id` GUC) as a backstop.
- `pgvector` cross-run source cache → **Phase 2** (YAGNI for v1).

---

## 8. Backend (FastAPI)

- Async, layered **routers → services → repositories**; Pydantic v2; config via **pydantic-settings**
  (env only, no embedded secrets).
- **[v2] DB:** one `AsyncSession` per request via DI, `expire_on_commit=False`; **PgBouncer (transaction
  mode)** in front of RDS; SQLAlchemy `NullPool`; asyncpg `statement_cache_size=0` (PgBouncer-compatible).
- **[v2] API:** `/v1` prefix; errors as **RFC 9457 problem+json**; **keyset pagination** for `GET /runs`
  (`created_at, id`); **`Idempotency-Key`** (UUID) required on `POST /runs`, stored key→run_id with TTL,
  worker enqueue uses `_job_id=<key>`.
- Endpoints: auth (`/register` [Turnstile], `/login`, `/refresh`, `/logout`), `POST /runs`, `GET /runs`,
  `GET /runs/{id}`, `GET /runs/{id}/events` (SSE), `POST /runs/{id}/cancel`, `POST /runs/{id}/export`.
- **[v2] SSE:** `sse-starlette` `EventSourceResponse` with `ping=15s`; headers `Cache-Control: no-cache`,
  `X-Accel-Buffering: no`; generator unsubscribes on `request.is_disconnected()`; events carry `id:` for
  `Last-Event-ID`. Authz-check the run owner on subscribe (per-run channel).
- Cross-cutting: structured JSON logging w/ `trace_id`/`span_id`/`request_id`, OTel traces, Prometheus
  `/metrics`, `/healthz` + `/readyz`.

---

## 9. Frontend (premium GUI — Cloudflare Worker static assets)

React + TypeScript + Vite + Tailwind + shadcn/ui. Screens: **New Research** (question + depth slider →
caps), **Live Run** (animated agent tree, token-streaming report, source cards as found), **Report**
(cited, collapsible, export), **History/Dashboard**.
- **[v2] Output safety (LLM05):** render Markdown with **raw HTML disabled** + **DOMPurify** sanitize;
  strict **CSP** (no `unsafe-inline`); sanitize source URLs/titles; tokens stored in httpOnly cookie or
  memory (never localStorage).
- Aesthetic: dark, editorial "research instrument," built via the frontend-design skill (not templated).

---

## 10. Infrastructure & ops (stack-as-code)

- **[v2] Docker:** multi-stage; **distroless/hardened base**; non-root, read-only FS, drop ALL caps,
  `no-new-privileges`, seccomp; **cosign-signed**, **SBOM (syft)** + **SLSA provenance** attested in CI.
- **docker-compose:** one command → full app live locally (postgres, redis, pgbouncer, api, worker, web).
  **This is the "real demo."**
- **[v2] Terraform (modular):** `network` (VPC; private subnets; **single NAT in dev / per-AZ prod**;
  **VPC endpoints** for S3/ECR/Secrets Manager/STS), `eks` (managed node group for add-ons + **Karpenter**
  / EKS Auto Mode for worker burst, Spot), `rds` (**Multi-AZ prod, KMS encryption, backups, deletion
  protection, forced TLS, gp3 autoscale**), `elasticache` (**Multi-AZ failover, in-transit+at-rest
  encryption, AUTH**), `s3`, `ecr` (**tag immutability**), `iam` (**Pod Identity**; IRSA fallback),
  `secrets`, `cloudflare` (Worker + DNS). Remote state: S3 (**versioned, KMS, public-access-block**) +
  **native locking**. **Separate state per env** (`envs/{dev,prod}`). `.terraform.lock.hcl` committed.
- **[v2] Kubernetes (Helm):** api Deployment (CPU HPA) + worker Deployment (**KEDA ScaledObject** on Redis
  depth, scale-to-zero); requests/limits on both; startup/liveness/readiness probes on both; **Restricted
  PSS** securityContext (`runAsNonRoot`, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation:false`)
  + namespace `pod-security…/enforce: restricted`; **default-deny NetworkPolicies** + explicit allows
  (api→pgbouncer/redis, worker→redis, worker→egress 443 only); **egress controls per §11.2**; PDBs;
  long `terminationGracePeriodSeconds` + `preStop` drain; **Alembic migration as Helm `pre-upgrade` hook**,
  expand-contract / backward-compatible, `CREATE INDEX CONCURRENTLY` (`transaction_per_migration`),
  `lock_timeout`, linted by **Squawk** in CI.
- **[v2] Cloudflare:** single **Worker** serves SPA static assets + edge JWT verify + rate-limit + proxy;
  SSE route returns the stream directly (no buffering helper) — **acceptance test asserts first-event
  latency through the Worker**. Provisioned via Cloudflare Terraform provider.
- **[v2] GitHub Actions:**
  - `ci.yml` — ruff + mypy + pytest + coverage; web lint/build; Trivy + **CodeQL** (Py+TS); top-level
    `permissions: {}`, per-job least-privilege; every action **SHA-pinned**; `concurrency` (cancel PRs).
  - `cd.yml` — **GitHub OIDC → AWS** (no static keys); build/sign/push ECR (by digest) → `helm upgrade`;
    runs under a GitHub **Environment with required reviewers**; serialized `concurrency`.
  - `pages.yml` → `web.yml` — deploy Worker (static assets) to Cloudflare (OIDC/scoped token).
  - `terraform.yml` — fmt/validate/plan on PR + **tfsec/Checkov** + **OPA/Conftest** policy gate; gated
    apply on main; **nightly drift-detection** plan.
  - **Dependabot** for pip/npm/actions.
- **[v2] Observability:** structured logs (trace-correlated) + Prometheus **RED** (api/worker) + queue
  **saturation**; OTel traces+metrics via **ADOT collector → CloudWatch OTLP endpoints**; LangGraph nodes
  instrumented with **OTel GenAI semantic conventions** (`gen_ai.*`: model, input/output tokens, agent
  spans) so per-step token/cost/latency is first-class telemetry. **SLOs** (run success rate; p95
  time-to-first-token) + error budgets. (No self-hosted Grafana/Tempo in v1.)

---

## 11. Security (hardening checklist) **[v2 — expanded; mapped to OWASP 2025 + RFC 8725]**

### 11.1 Agentic / LLM (OWASP LLM Top 10 2025)
- [ ] **LLM01 indirect prompt injection:** all fetched/extracted web content wrapped in untrusted-data
      delimiters (spotlighting); models told to treat it as data, never instructions.
- [ ] **Dual-LLM / quarantine:** the content-ingesting node has **no tools** and **cannot mutate run
      state**; a privileged node consumes only its *validated structured output*.
- [ ] **"Rule of Two":** no single node simultaneously (a) reads untrusted input, (b) holds sensitive
      creds, (c) changes external state, without a gate.
- [ ] **LLM05 output handling:** Markdown raw-HTML disabled + DOMPurify; strict CSP; source URLs/titles
      sanitized (XSS via model output that embeds attacker page text).
- [ ] **LLM10 unbounded consumption:** per-run token cap, per-user daily quota, per-provider cost meters,
      **global daily spend kill-switch**, critic loop hard-capped server-side, Turnstile on register.

### 11.2 SSRF & egress (OWASP A01:2025 — the worker fetches attacker-controlled URLs)
- [ ] Worker/API pods: **default-deny egress** NetworkPolicy; allowlist provider egress only (ideally via
      an egress proxy).
- [ ] **IMDSv2 enforced, hop-limit 1**; `169.254.169.254` + RFC1918 + loopback + link-local + IPv6 ULA
      blocked at egress (prevents SSRF→IMDS credential theft).
- [ ] URL fetch validation = **allowlist** scheme/host; **resolve-then-pin IP** (defeat DNS rebinding);
      reject redirects into private ranges.

### 11.3 AuthN/AuthZ (OWASP A07:2025 / RFC 8725)
- [ ] JWT: **pin alg allowlist** (reject `none`, HS↔RS confusion); validate `aud`+`iss`; sanitize `kid`;
      never follow `jku`/`x5u`. Access TTL ~10 min; **refresh rotation + reuse detection (token families)**;
      **revocation via Redis `jti` deny-list** (TTL=token life) checked each request; logout revokes.
- [ ] Edge Worker does **full signature validation**, not a presence check.
- [ ] **argon2id**, m=19456 (19 MiB), t=2, p=1 (or m=47104,t=1,p=1); login throttling/lockout;
      breached-password check.
- [ ] Per-user isolation enforced **and tested** on **every** `{id}` endpoint incl. SSE subscribe and S3
      export keys (short-lived **pre-signed**, never public). **Cross-tenant access test in CI** (expect 403/404).

### 11.4 Secrets & supply chain (A03/A04:2025)
- [ ] No secrets in images/git (CI **gitleaks** scan); Secrets Manager rotation automated + documented.
- [ ] CI: **SBOM** (syft), **cosign** signing + **admission verification** (reject unsigned), pinned
      base-image **digests**, lockfiles + `pip-audit`/`npm audit`, **Trivy gate fails on Critical/High**.
- [ ] Containers per §10 (non-root, read-only FS, drop caps, seccomp).

### 11.5 Data, logging, errors (A08/A09/A10:2025)
- [ ] **Log/trace PII redaction** for questions, `run_steps.payload`, fetched content.
- [ ] Encryption at rest (RDS/ElastiCache/S3) + TLS in transit, explicit in Terraform.
- [ ] **Data retention + user-deletion (erasure)** policy.
- [ ] **Security alerting** (auth spikes, budget breach, egress deny), not just metrics.
- [ ] Global error handler **fails closed**; no stack-trace leakage; cancel/budget-kill never bypass
      authz or egress checks.

---

## 12. Testing **[v2]**

- **Backend:** pytest + pytest-asyncio; API tests via `httpx` against throwaway Postgres (testcontainers).
- **Agent determinism:** **record/replay cassettes** (VCR/`pytest-recording`) for tool-call sequences +
  hand-mocks; a couple of live "smoke" tests gated behind a flag.
- **[v2] Agent quality eval harness** (scheduled/gated, not per-PR): fixed question set scoring **citation
  faithfulness/groundedness**, no-uncited-claims invariant, completeness, source diversity.
- **[v2] Contract tests** for the `SearchProvider` interface (Tavily/Anthropic/Exa) against fixtures.
- **[v2] SSE tests:** event ordering, heartbeats, client-disconnect/cancel propagation, **cross-pod stream
  relay**, `Last-Event-ID` replay.
- **[v2] Cross-tenant authz tests** (every `{id}` endpoint) in the CI coverage gate.
- **[v2] Load test** (k6/Locust) of the SSE + queue + KEDA path.
- **Frontend:** Vitest + Playwright e2e on the local stack.
- **Coverage gate:** explicit threshold, **ratchet-only** (never lower).

---

## 13. Release strategy **[v2]**

Immutable image tags (deploy by **digest**; ECR tag immutability) · `helm rollback` runbook ·
expand-contract migrations make deploys reversible without down-migrations · API tier: `maxUnavailable: 0`
+ graceful SSE drain so in-flight streams survive rollouts (canary/blue-green optional later) ·
Argo CD GitOps deferred to a later phase (ADR).

---

## 14. Repository layout

```
atlas/
  apps/api/         FastAPI, agent graph, alembic
  apps/web/         React + Vite SPA
  infra/terraform/  modules/ + envs/{dev,prod}   (separate state per env)
  infra/k8s/        Helm chart (incl. KEDA ScaledObject, migration pre-upgrade hook)
  infra/cloudflare/ Worker (static assets + edge proxy)
  .github/workflows/
  docs/             architecture (C4 + sequence), ADRs, runbooks, threat model, cost notes
  docker-compose.yml
  README.md         premium: architecture diagram + quickstart + tech map
```

---

## 15. Milestones (sequenced; each independently valuable)

| Milestone | Delivers | Definition of done |
|---|---|---|
| **M1 — Working product (local)** | FastAPI + Postgres + LangGraph agents (Send fan-out, checkpointer, structured output, entailment verify) + Redis-Stream SSE + React; cost guardrails; cancellation; LLM01/LLM05 controls | `docker compose up` → submit → watch agent tree → cited report; mocked/replay agent tests + cross-tenant authz tests green |
| **M2 — Productionize** | Distroless signed images (cosign/SBOM/SLSA), Helm chart (KEDA, probes, PSS, migration hook), GitHub Actions CI (OIDC, SHA-pinned, CodeQL, Trivy gate) | Green CI; Trivy clean; deployable signed artifacts |
| **M3 — Cloud** | Terraform (VPC+endpoints / EKS+Karpenter / RDS Multi-AZ / ElastiCache / S3 / ECR / **Pod Identity** / native-lock state, per-env) + Cloudflare Worker + CD (OIDC, env approvals, drift) + egress/IMDSv2 hardening | `terraform apply` + push → live on user's accounts; SSE streams through the Worker |
| **M4 — Docs** | C4 + sequence diagrams, ADRs (incl. Helm-vs-Argo, Pod-Identity), runbooks, **threat model enumerating indirect-prompt-injection + SSRF→IMDS**, cost notes, "how each required tech is used" map | Comprehensive docs deliverable complete |

Full required stack (FastAPI, Postgres, Agentic AI, K8s, AWS, Terraform, GitHub Actions, Cloudflare)
covered across M1–M4; nothing cut, only sequenced.

---

## 16. Open items to confirm at coding time

- Exact Claude model IDs + tool-use/structured-output/Citations schema — **verify against current Claude
  API reference** (do not code from memory).
- Tavily/Anthropic/Exa keys (user supplies at deploy).
- Redis Stream retention window vs expected reconnect gap; load-test DB connection count at max KEDA
  replicas against RDS `max_connections` (PgBouncer sizing).
- Final cap values + global spend ceiling (tune after first live runs).
