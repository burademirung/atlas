# The required stack — and where each piece lives

Every required technology is present as **real, working code** in this repository (not just
described in a design doc). This file is the map.

| # | Required skill | Where it lives | Evidence it's real |
|---|---|---|---|
| 1 | **Python + FastAPI** — build a backend from scratch | [`apps/api/`](apps/api/) | Async FastAPI, layered routers→services→repositories, Pydantic v2, 24 passing tests (`uv run pytest`), `ruff` + `mypy --strict` clean. |
| 2 | **PostgreSQL** — as a production database | [`apps/api/src/atlas_api/db/models.py`](apps/api/src/atlas_api/db/models.py), [`migrations/`](apps/api/src/atlas_api/migrations/) | SQLAlchemy 2.0 async, 7-table schema with a join table + CASCADE FKs, Alembic migration, tested against real Postgres via testcontainers. |
| 3 | **Agentic AI** — multi-agent systems with LangGraph / Claude | [`apps/api/src/atlas_api/agents/`](apps/api/src/atlas_api/agents/) | A LangGraph `StateGraph`: **plan → [search ×N in parallel via `Send`] → verify → write**, driven by Claude (`langchain-anthropic`), with a pluggable `SearchProvider` (Tavily + stub). Deterministic tests in `tests/test_agents.py`. Also deployed live (Claude + web search) in [`apps/cloudflare/`](apps/cloudflare/). |
| 4 | **Terraform** — author cloud infrastructure as code | [`infra/terraform/`](infra/terraform/) | Modular AWS + Cloudflare: `modules/{network,eks,rds,elasticache,ecr,iam,s3,cloudflare}`, separate root config + S3-native-locked state per env (`envs/dev`, `envs/prod`). `terraform fmt` clean. |
| 5 | **Kubernetes** — run containers in production | [`infra/k8s/atlas/`](infra/k8s/atlas/) | A Helm chart: API + arq worker Deployments, **KEDA** queue-depth autoscaling, ALB Ingress, External Secrets, Alembic pre-upgrade migration hook, Restricted PodSecurity, NetworkPolicies, PDBs. |
| 6 | **AWS** — own an environment end to end | [`infra/terraform/modules/`](infra/terraform/modules/) | EKS (Pod Identity), RDS PostgreSQL (Multi-AZ, KMS), ElastiCache Redis, S3, ECR (immutable), IAM least-privilege, VPC + endpoints — all defined and wired. |
| 7 | **GitHub Actions** — the pipeline that tests and ships | [`.github/workflows/`](.github/workflows/) | `ci.yml` (ruff/mypy/pytest + Trivy + gitleaks), `codeql.yml`, `cd.yml` (OIDC→AWS, build/sign/SBOM → ECR by digest → `helm upgrade` on EKS, gated by a `production` environment), `pages.yml` (Cloudflare), `terraform.yml` (fmt/validate/plan). `actionlint` clean. |

## Two editions of the same product

- **Live edition** (deployed: <https://atlas-research.burademirung.workers.dev>) — Cloudflare Worker +
  Claude Opus 4.8 web search + D1. Zero servers to manage. Proves Agentic AI + Cloudflare end to end.
- **Production edition** — FastAPI + LangGraph agents + PostgreSQL on Kubernetes (AWS EKS), all
  provisioned by Terraform and shipped by GitHub Actions. This is where requirements 1, 2, 4, 5, 6, 7
  live as code, ready for `terraform apply` + a push.

See [`docs/superpowers/specs/2026-06-29-deep-research-studio-design.md`](docs/superpowers/specs/2026-06-29-deep-research-studio-design.md)
for the full architecture and the multi-domain review behind it.
