# Contributing

> How to set up, branch, commit, test, and open a pull request for Firstline / Atlas.
> AI agents: read [`AGENTS.md`](AGENTS.md) first. Full dev setup: [`docs/development.md`](docs/development.md).

Thanks for contributing! This repo is a security incident-response product with two editions
(a live Cloudflare Worker and a production FastAPI/Kubernetes stack). Please keep changes honest
about what is implemented vs planned, and never weaken the [security guardrails](AGENTS.md#security-guardrails-must-respect).

## 1. Prerequisites

- **Python 3.12** and [`uv`](https://docs.astral.sh/uv/) (for `apps/api`)
- **Node.js** (LTS) + npm (for `apps/cloudflare` and `apps/web`)
- **Docker** + Docker Compose (for the full local stack)
- Optional: `terraform` ≥ 1.10 and `helm` (for `infra/`)

## 2. Set up

```bash
# Backend
cd apps/api && uv sync --all-groups

# Live Worker
cd apps/cloudflare && npm install

# Web SPA
cd apps/web && npm ci

# Or just run the whole production edition locally:
docker compose up --build      # web → http://localhost:8081 · API docs → http://localhost:8080/docs
```

See [`docs/development.md`](docs/development.md) for environment variables (from
[`.env.example`](.env.example)) and how to run each service individually.

## 3. Branch

Create a topic branch off `main`:

```bash
git switch -c feat/short-description     # or fix/…, docs/…, chore/…
```

Do not commit directly to `main`; it is the deploy branch (CD and the Cloudflare/Terraform
workflows trigger from it).

## 4. Commit — Conventional Commits

This repo uses [Conventional Commits](https://www.conventionalcommits.org/). Format:

```
<type>(<optional scope>): <summary>
```

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`. Scopes seen in history
include `api`, `cloudflare`, `web`, `infra`, `k8s`, `evals`. Examples:

```
feat(api): add per-user daily run quota
fix(cloudflare): handle web_search error frames
docs: document the SSE event shapes
```

Keep secrets out of commits — CI runs gitleaks and Trivy secret scans.

## 5. Test, lint, type-check

Run the checks for whatever you touched (see the [Definition of done](AGENTS.md#definition-of-done)):

```bash
# apps/api
cd apps/api
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest

# apps/cloudflare
cd apps/cloudflare && npm run typecheck && npm test

# apps/web
cd apps/web && npm run build

# infra
cd infra/terraform/envs/dev && terraform fmt -check && terraform validate
```

More on the test strategy: [`docs/testing.md`](docs/testing.md).

## 6. Open a pull request

1. Push your branch and open a PR against `main`.
2. Describe **what** changed and **why**; note anything you marked planned vs implemented.
3. CI must be green: `ci.yml` (ruff/mypy/pytest + Trivy + gitleaks), `codeql.yml`, and — if you
   touched `infra/terraform/**` — `terraform.yml` (fmt/validate/plan).
4. Be ready for review. `cd.yml` (deploy) and the Terraform `plan` on `main` run behind gated
   GitHub Environments with required reviewers — a human approves before anything ships.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report concerns to
<burademirung@gmail.com>. To report a security vulnerability, follow [`SECURITY.md`](SECURITY.md).
</content>
