# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Comprehensive documentation set: `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, this changelog, and `docs/` guides (documentation index, development,
  deployment, API reference, testing, observability, data model, security, agent design, and a
  documentation-strategy rationale).

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
</content>
