# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Security headers on every response (live edition):** a strict `Content-Security-Policy` plus
  `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
  `Permissions-Policy`, and `X-Frame-Options: DENY` — applied to `/api/*` and the SSE stream via a
  `withSecurityHeaders()` wrapper in `apps/cloudflare/src/index.ts` and to static assets via a new
  `public/_headers` file.
- **PII redaction:** `redact_pii` (`apps/api/.../security/redaction.py`) and `redactPII` (Worker)
  mask SSNs, Luhn-validated cards, emails, and phone numbers in the breach description **before** it
  is persisted; a `RedactionFilter` on the root log handler scrubs PII from all logs. The model still
  receives the original text in-memory; the generated report is intentionally not redacted.
- **Denial-of-wallet guardrails (production, OWASP LLM10):** `security/guardrails.py` adds a global
  kill-switch (`service_paused` → 503), per-user (50/day) and per-IP (200/day) Redis daily quotas
  (429), `Idempotency-Key` dedupe, and a per-run token ceiling (truncates the run). New settings:
  `service_paused`, `max_output_tokens`, `max_run_tokens`, `max_tool_calls`, `daily_run_quota`,
  `daily_run_quota_ip`, `idempotency_ttl_seconds`, `trusted_proxy_count`.
- **30-day retention + self-service erasure (live edition):** a Cloudflare cron (`"17 3 * * *"`) +
  `scheduled()` handler purges runs/sources older than 30 days and stale rate-limit rows;
  `DELETE /api/runs/:id` deletes a run + its sources on demand (204).
- **`data_types` wired end to end (production):** `RunCreateIn.data_types` →
  `runs/repository.py` (persisted on the run `config`) → `worker.py` → the graph, so breach playbooks
  are now injected on the `POST /v1/runs` path. `POST /v1/runs` also accepts an `Idempotency-Key`
  header.
- **Observability implemented (production):** OpenTelemetry GenAI-semconv tracing
  (`observability/telemetry.py`, active when `OTEL_EXPORTER_OTLP_ENDPOINT` is set — no-op otherwise),
  Prometheus RED + run/token metrics (`observability/metrics.py`), and a `/metrics` endpoint. New
  settings: `otel_exporter_otlp_endpoint`, `otel_service_name`.
- **Security disclosure:** `apps/cloudflare/public/.well-known/security.txt` (RFC 9116); a privacy
  note in the live edition `index.html`.
- **Repo governance:** `LICENSE` (MIT), `.editorconfig`, `.pre-commit-config.yaml` (ruff, hooks,
  gitleaks), `.github/CODEOWNERS`, a PR template, and three issue templates.
- **CI:** a coverage gate (`--cov-fail-under=85`), Semgrep SAST, and Bandit (report-only SARIF).
- **Docs:** new `docs/compliance.md` (privacy & GDPR/CCPA/HIPAA posture); updated `security.md`,
  `threat-model.md`, `data-model.md`, `observability.md`, and `api-reference.md` to reflect the
  shipped controls. Earlier: the comprehensive documentation set (`AGENTS.md`, `CONTRIBUTING.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, this changelog, and the `docs/` guides).

### Changed

- Threat model and security docs flip denial-of-wallet, missing-CSP, and PII-at-rest from
  planned/partial to implemented; the data model documents redaction-on-write and the persisted
  `data_types`; observability moves from "planned" to "implemented" (with the no-op-without-collector
  caveat for OTel export).

### Security

- **Fixed a HIGH "quota bypass via X-Forwarded-For spoofing" finding.**
  `client_ip(request, trusted_proxy_count)` now reads the **right-most trusted** XFF hop (appended by
  the ALB) instead of the attacker-controlled left-most value, so a client can no longer forge a
  fresh per-IP quota key per request. `trusted_proxy_count` defaults to 1; `0` uses the socket peer.

### Notes

- The product was **pivoted to "Firstline"** (breach-response copilot) on top of the original
  "Atlas — Deep-Research Studio" engine. Branding is mixed across the codebase: the Python package
  remains `atlas_api` and several infra docs use the "Atlas" codename, while the agent prompts, the
  live Worker, the breach playbooks, and the MCP server are "Firstline".

## [0.1.0] — 2026-06-29

Initial code-complete release. Both editions of the product exist as real, working code; the live
Cloudflare edition is deployed, and the production edition runs locally via `docker compose up`
with its cloud deploy code-complete (IaC + CI/CD).

### Added

**Live (Cloudflare) edition** ([`apps/cloudflare/`](apps/cloudflare/))

- A single Cloudflare Worker (`src/index.ts`) running Claude Opus 4.8 with the native `web_search`
  server tool, constrained to an allow-list of authoritative domains (FTC, CISA, NIST, credit
  bureaus, …); streams a prioritized, cited breach-recovery plan over SSE and persists runs to D1.
- Prompt-injection spotlighting (untrusted-content framing), per-request caps (≤ 500 chars,
  `max_uses: 5`, `max_tokens: 6000`), per-IP/global daily rate-limit table, and optional Turnstile
  bot verification. D1 migrations for `runs`, `sources`, and `rate_limits`.
- Vanilla SPA assets in `public/` (served via the `ASSETS` binding) with an animated architecture
  explainer.

**Production edition** ([`apps/api/`](apps/api/), [`apps/web/`](apps/web/))

- Async FastAPI service (`atlas_api`): layered routers → services → repositories, Pydantic v2
  settings, RFC-9457 problem responses, request-id middleware, health/readiness endpoints.
- Authentication: RFC 8725 JWT (algorithm allowlist, required claims), short access TTL, refresh
  rotation with reuse detection (Redis token-family revocation), access deny-list, argon2id hashing.
- Runs API: create (202 + arq enqueue, idempotent `_job_id`), list, detail, cancel, and an SSE
  events endpoint backed by **Redis Streams** (replayable via `Last-Event-ID`).
- LangGraph research graph (`agents/`): plan → parallel search (`Send` fan-out) → verify → write,
  with a pluggable `SearchProvider` (Tavily + deterministic stub) and Claude via `langchain-anthropic`.
- Breach domain (`breach/`): curated Markdown recovery playbooks per leaked data type, a
  breach-notification law table, and a Have I Been Pwned client (k-anonymity password check).
- Firstline MCP server (`mcp_server.py`, FastMCP) exposing breach-response tools.
- arq worker (`worker.py`) running the graph and streaming progress to Redis; agent-quality eval
  harness (`evals/`). PostgreSQL 7-table schema (SQLAlchemy 2.0 async) with an Alembic baseline.
- React + Vite SPA (`apps/web/`) wired to the `/v1` API with fetch-based SSE streaming.

**Infrastructure & CI/CD** ([`infra/`](infra/), [`.github/`](.github/))

- Terraform: modular AWS (EKS, RDS, ElastiCache, S3, ECR, IAM Pod Identity, VPC) + Cloudflare, with
  separate root config + S3-native-locked state per environment (`envs/dev`, `envs/prod`).
- Helm chart (`infra/k8s/atlas/`): API + worker Deployments, KEDA queue-depth autoscaling
  (scale-to-zero), ALB Ingress, External Secrets, an Alembic pre-upgrade migration hook, Restricted
  Pod Security, NetworkPolicies, and PodDisruptionBudgets.
- GitHub Actions: `ci` (ruff/mypy/pytest + Trivy + gitleaks), `codeql`, `cd` (OIDC → AWS, cosign +
  SBOM → ECR by digest → `helm upgrade` on EKS, gated by a `production` environment), `pages`
  (Cloudflare Worker deploy), `terraform` (fmt/validate/plan), and a scheduled `eval`.
- Local stack: `docker-compose.yml` (Postgres + Redis + PgBouncer + migrate + API + worker + web).

### Documentation

- `docs/architecture.md` (C4 + sequence + data model), `docs/runbook.md`, `docs/threat-model.md`,
  `docs/cost-notes.md`, and ADRs `0001`–`0005`.

[Unreleased]: https://github.com/burademirung/atlas/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/burademirung/atlas/releases/tag/v0.1.0
