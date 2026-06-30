# Documentation

> The map of all Firstline / Atlas documentation, organized by the
> [Diátaxis](https://diataxis.fr/) framework (Tutorials · How-to guides · Reference · Explanation).
> New here? Start with the root [`README.md`](../README.md), then [`AGENTS.md`](../AGENTS.md).

Firstline is a security incident-response copilot built as two editions of one product — a **live**
Cloudflare Worker edition and a **production** FastAPI/LangGraph/Kubernetes edition. The docs below
cover both; each page marks clearly what is implemented vs planned and which edition it applies to.

## Tutorials — learning-oriented

Get the system running and see the request → stream → cited-report loop end to end.

| Doc | What you'll do |
|---|---|
| [Development setup](development.md) | Run `apps/api`, the arq worker, the live Worker, the web SPA, and the full `docker compose` stack locally |
| Root [Quickstart](../README.md#quickstart) | `docker compose up` (production edition) and `wrangler dev` (live edition) |

## How-to guides — task-oriented

| Doc | Task |
|---|---|
| [Deployment](deployment.md) | Deploy the live (Cloudflare) and production (Terraform + Helm on EKS) editions |
| [Runbook](runbook.md) | Operate both editions: secrets/env, migrations, rollback, eval, failure modes |
| [Testing](testing.md) | Run and write tests (pytest + testcontainers, Vitest, deterministic agent tests, evals) |
| [Contributing](../CONTRIBUTING.md) | Set up, branch, commit (Conventional Commits), and open a PR |

## Reference — information-oriented

| Doc | Describes |
|---|---|
| [API reference](api-reference.md) | The Worker (`/api/*`) and FastAPI (`/v1/*`) HTTP surfaces + SSE event shapes |
| [Data model](data-model.md) | The PostgreSQL 7-table schema and the Cloudflare D1 schema |
| [`STACK.md`](../STACK.md) | Where each required technology lives, with evidence |
| [`AGENTS.md`](../AGENTS.md) | Commands, conventions, and guardrails for AI coding agents |
| [`.github/WORKFLOWS.md`](../.github/WORKFLOWS.md) | The CI/CD pipeline (workflows, environments, OIDC setup) |
| [`infra/terraform/README.md`](../infra/terraform/README.md) | Terraform module map and dev-vs-prod table |
| [`infra/k8s/atlas/README.md`](../infra/k8s/atlas/README.md) | The Helm chart, prerequisites, and key values |
| [`apps/api/README.md`](../apps/api/README.md) | Backend dev quickstart |

## Explanation — understanding-oriented

| Doc | Explains |
|---|---|
| [Architecture](architecture.md) | C4 context/container views, the request sequence, and the data model |
| [Agent design](agent-design.md) | The LangGraph graph, parallel fan-out, the verify node, spotlighting, playbooks, MCP, evals |
| [Security](security.md) | Defense-in-depth security architecture, mapped to OWASP/NIST (headers/CSP, PII redaction, denial-of-wallet) |
| [Threat model](threat-model.md) | Attack paths + mitigations (prompt injection, denial-of-wallet, XSS, SSRF, authn/z, secrets, PII) |
| [Compliance](compliance.md) | Privacy & compliance posture — GDPR / CCPA / HIPAA, redaction, retention, erasure |
| [Observability](observability.md) | Logging, metrics, and tracing (implemented: Prometheus + OTel GenAI semconv) |
| [Cost notes](cost-notes.md) | Cost model for both editions and how to keep dev cheap |
| [Documentation strategy](documentation-strategy.md) | Why this doc set exists and the standards behind it |

## Decisions (ADRs)

Architecture Decision Records live in [`adr/`](adr/):

| ADR | Decision |
|---|---|
| [0001](adr/0001-cloudflare-vs-aws-editions.md) | Two editions: Cloudflare (live) and AWS (production) |
| [0002](adr/0002-langgraph-multi-agent.md) | LangGraph for the multi-agent research graph |
| [0003](adr/0003-sse-redis-streams-not-pubsub.md) | SSE backed by Redis Streams, not pub/sub |
| [0004](adr/0004-keda-for-queue-autoscaling.md) | KEDA for worker queue-depth autoscaling |
| [0005](adr/0005-terraform-per-env-state.md) | Terraform: separate root config + state per environment |

## Project meta

- [`CHANGELOG.md`](../CHANGELOG.md) — Keep a Changelog history
- [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) — Contributor Covenant 2.1
- [`SECURITY.md`](../SECURITY.md) — vulnerability disclosure policy
- [`docs/superpowers/specs/`](superpowers/) — the original design spec and implementation plan (historical context)
