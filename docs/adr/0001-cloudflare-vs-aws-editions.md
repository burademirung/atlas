# ADR 0001 — Two editions: Cloudflare (live) and AWS (production)

**Status:** Accepted · 2026-06-29

## Context

Atlas must (a) be a *real, deployed, working* research product someone can use today, and (b)
demonstrate a complete production-grade stack: FastAPI, PostgreSQL, agentic AI, Kubernetes, AWS,
Terraform, GitHub Actions, Cloudflare. Optimizing one goal compromises the other: a full EKS stack
is not "click a link and it works," while a single serverless Worker doesn't exercise Kubernetes,
RDS, Terraform, or a real backend.

## Decision

Ship **two editions of the same product** from one repo, sharing the design but making opposite
infrastructure trade-offs.

- **Live (Cloudflare) edition** ([`apps/cloudflare/`](../../apps/cloudflare/)) — one Worker running
  Claude Opus 4.8 with the native `web_search` server tool, backed by D1. Zero servers, deployed and
  publicly reachable. Proves Agentic AI + Cloudflare end to end.
- **Production edition** ([`apps/api/`](../../apps/api/) + [`infra/`](../../infra/)) — FastAPI +
  LangGraph agent workers on EKS, PostgreSQL, Redis, all provisioned by Terraform and shipped by
  GitHub Actions. This is where the remaining six required technologies live as code, runnable
  locally via `docker compose up` and deployable to the operator's own AWS/Cloudflare accounts.

## Consequences

- **+** Both goals met: a working public demo *and* a complete, auditable production stack.
- **+** The editions share concepts (SSE streaming, untrusted-content handling, cited reports), so
  the design reads consistently across both.
- **+** The live edition de-risks the agent/UX; the production edition de-risks the infra.
- **−** Two codebases for the agent (TypeScript Worker vs Python LangGraph) — some duplicated logic
  (prompts, SSE event shapes) that can drift.
- **−** Two D1 vs Postgres schemas to keep conceptually aligned.
- The production edition's cloud deploy is **operator-applied** (own credentials), not continuously
  hosted by us — a deliberate cost/ownership choice (see ADR 0005 and the runbook).
