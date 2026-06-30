# Atlas — Operations Runbook

How to deploy, configure, migrate, roll back, and troubleshoot both editions of Atlas. Commands
assume you are at the repo root unless a `cd` is shown.

- **Live (Cloudflare) edition** — one Worker, deployed with `wrangler`.
- **Production edition** — Terraform-provisioned AWS + Cloudflare, shipped with Helm via GitHub
  Actions.

---

## 1. Deploy

### 1a. Live (Cloudflare) edition

Code: [`apps/cloudflare/`](../apps/cloudflare/). CI: [`.github/workflows/pages.yml`](../.github/workflows/pages.yml).

**Automated (preferred):** push to `main` touching `apps/cloudflare/**`. The `Deploy Worker`
workflow type-checks (`tsc --noEmit`) and runs `wrangler deploy` using a **scoped**
`CLOUDFLARE_API_TOKEN` secret + `CLOUDFLARE_ACCOUNT_ID` variable, gated by the
`cloudflare-production` GitHub Environment.

**Manual:**

```bash
cd apps/cloudflare
npm ci
npx wrangler secret put ANTHROPIC_API_KEY          # one-time, per environment
npx wrangler d1 migrations apply atlas-research      # apply D1 schema (drop --local for remote)
npx wrangler deploy
```

`wrangler.jsonc` binds the D1 database (`DB`), static assets (`ASSETS`, SPA fallback), and the
Workers AI binding (`AI`). The deployed URL is <https://atlas-research.burademirung.workers.dev>.

### 1b. Production edition — infra (Terraform)

Code: [`infra/terraform/`](../infra/terraform/). CI: [`.github/workflows/terraform.yml`](../.github/workflows/terraform.yml).

The deploy model is **"the operator applies with their own AWS/Cloudflare credentials."** CI runs
`fmt`/`validate`/`plan` (PRs) and a gated read-only `plan` on `main`; **`apply` is deliberately a
human-run step.**

Prerequisites: Terraform ≥ 1.10 (native S3 state locking), an existing versioned + SSE-KMS state
bucket per account, AWS credentials, and a Cloudflare API token + zone/account IDs.

```bash
cd infra/terraform/envs/dev        # or envs/prod — separate root config + state per env
cp terraform.tfvars.example terraform.tfvars && $EDITOR terraform.tfvars
$EDITOR backend.tf                 # point bucket/key/region at YOUR state bucket
export TF_VAR_cloudflare_api_token=...   # never in tfvars
terraform init
terraform plan  -out tfplan
terraform apply tfplan
```

This provisions VPC (single NAT in dev / per-AZ in prod) + endpoints, EKS (Pod Identity), RDS
PostgreSQL (Multi-AZ + deletion protection in prod), ElastiCache Redis, S3, ECR, IAM, and the
Cloudflare Worker/DNS. The RDS master password and Redis AUTH token are generated and written to
**AWS Secrets Manager** — read them from there. See [`infra/terraform/README.md`](../infra/terraform/README.md)
for the full module map and the dev-vs-prod table.

**Cluster add-ons** (installed once, separate lifecycle from the app): KEDA, External Secrets
Operator, AWS Load Balancer Controller, a NetworkPolicy-enforcing CNI, metrics-server. See
[`infra/k8s/README.md`](../infra/k8s/README.md).

### 1c. Production edition — application (Helm via CD)

Code: [`infra/k8s/atlas/`](../infra/k8s/atlas/). CI: [`.github/workflows/cd.yml`](../.github/workflows/cd.yml).

**Automated (preferred):** push to `main` or a `v*` tag triggers `CD`, which:

1. Builds 3 images (`api`, `worker`, `web`) — `api` and `worker` share `apps/api/Dockerfile`.
2. Signs them with **cosign** (keyless OIDC), attaches an **SBOM** (syft) + SLSA provenance.
3. Pushes to **ECR addressed by digest** (immutable).
4. `helm upgrade --install atlas infra/k8s --atomic --wait` pinning every image **by digest**.

The deploy job runs inside the `production` GitHub Environment (required reviewers), so a human
approves before anything reaches the cluster. AWS access is **GitHub OIDC** (no static keys).

**Manual Helm:**

```bash
aws eks update-kubeconfig --name <cluster> --region <region>
helm upgrade --install atlas infra/k8s/atlas \
  --namespace atlas --create-namespace \
  --values infra/k8s/atlas/values.yaml \
  --set-string image.registry=<acct>.dkr.ecr.<region>.amazonaws.com \
  --atomic --wait --timeout 10m
kubectl -n atlas rollout status deployment/atlas-api --timeout=5m
```

The Alembic migration runs automatically as a Helm **pre-upgrade hook** before the new pods roll
(see §3).

---

## 2. Required secrets & environment

### Application env (FastAPI / worker)

Read by `pydantic-settings` ([`config.py`](../apps/api/src/atlas_api/config.py)); env-only, no
embedded secrets.

| Var | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://…@pgbouncer:6432/atlas` — **always via PgBouncer**, never RDS direct |
| `REDIS_URL` | ✅ | arq queue + per-run Streams + JWT jti deny-list (use `rediss://` for TLS) |
| `JWT_SECRET` | ✅ | HS256 signing secret (≥ 32 chars) |
| `ANTHROPIC_API_KEY` | ✅ for real runs | Claude API; absent → worker uses stub search but `write`/`plan` need a model |
| `TAVILY_API_KEY` | optional | live web search; absent → deterministic stub provider |
| `RESEARCH_MODEL` | optional | default `claude-opus-4-8` |
| `ENVIRONMENT` | optional | `dev` / `production` |

JWT knobs (`JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_ALGORITHM`, `ACCESS_TTL_SECONDS=600`,
`REFRESH_TTL_SECONDS`) and argon2 params have safe defaults.

### Where secrets live per environment

| Environment | Secret store | Mechanism |
|---|---|---|
| Local (`docker compose`) | `docker-compose.yml` + shell | dev `JWT_SECRET`; `ANTHROPIC_API_KEY`/`TAVILY_API_KEY` from your shell |
| Cloudflare edition | Cloudflare Worker secrets | `wrangler secret put ANTHROPIC_API_KEY` (optional `TURNSTILE_SECRET`) |
| Production (EKS) | **AWS Secrets Manager** → **External Secrets Operator** → k8s Secret (`envFrom`) | keys `atlas/prod/app` (jwt), `atlas/prod/providers` (anthropic/tavily), `atlas/prod/db` (password); see [`values.yaml`](../infra/k8s/atlas/values.yaml) `externalSecrets` |

### CI/CD secrets & variables (GitHub)

| Name | Type | Used by |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | var | CD — OIDC role assumed to push ECR + `helm upgrade` |
| `AWS_TF_PLAN_ROLE_ARN` | var | Terraform — read-only OIDC role for gated plan |
| `AWS_REGION`, `ECR_REGISTRY`, `EKS_CLUSTER_NAME`, `APP_URL` | vars | CD |
| `CLOUDFLARE_API_TOKEN` | secret | Worker deploy (scoped token; OIDC not yet supported by wrangler) |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_WORKER_URL` | vars | Worker deploy |
| `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` | secrets | weekly agent-quality eval |

No long-lived AWS keys exist anywhere — AWS access is always GitHub **OIDC → assume role**.

---

## 3. Database migrations (Alembic)

Migrations live in [`apps/api/src/atlas_api/migrations/`](../apps/api/src/atlas_api/migrations/);
config in `apps/api/alembic.ini`.

**Local:** the `migrate` compose service runs `alembic upgrade head` before `api`/`worker` start.
Run by hand:

```bash
cd apps/api
uv run alembic upgrade head           # apply
uv run alembic revision --autogenerate -m "describe change"
uv run alembic downgrade -1           # local only
```

**Production:** the Helm chart runs the migration as a **`pre-upgrade` hook Job**
([`templates/migration-job.yaml`](../infra/k8s/atlas/templates/migration-job.yaml), reusing the API
image, `alembic upgrade head`) **before** new app pods roll. Use **expand-contract /
backward-compatible** migrations only, so a `helm rollback` to the previous image still works
against the new schema — never write down-migrations into the rollout path. The hook has
`backoffLimit: 1` and `activeDeadlineSeconds: 600`; if it fails, the upgrade aborts before any new
pod serves traffic.

---

## 4. Rollback

**Production app (Helm):**

```bash
helm history atlas -n atlas
helm rollback atlas <REVISION> -n atlas --wait --timeout 10m
kubectl -n atlas rollout status deployment/atlas-api --timeout=5m
```

Because images are pinned by **immutable digest** and migrations are expand-contract, rolling back
the release rolls back to the exact previous artifact without a schema down-migration. The API tier
uses `maxUnavailable: 0` + a `preStop` drain so in-flight SSE streams survive the rollout.

**Cloudflare edition:** `npx wrangler rollback` (or `wrangler deployments list` → roll back to a
prior version). D1 has no automatic rollback — forward-only migrations.

**Infra (Terraform):** revert the offending commit and `terraform apply` the prior plan. Be careful
with stateful resources (RDS deletion protection is on in prod; ElastiCache/RDS changes may force
replacement — read the plan).

---

## 5. Watching the agent-quality eval

The eval scores groundedness / no-uncited-claims / source diversity over a fixed question set.

- **Per-PR (cheap, structural):** `apps/api/tests/test_evals.py` via the stub provider — runs in CI
  on every PR, no API cost.
- **Scheduled (live):** [`.github/workflows/eval.yml`](../.github/workflows/eval.yml) — Mondays
  07:00 UTC + manual `workflow_dispatch`. Uses the real Claude + Tavily keys; runs
  `uv run python -m atlas_api.evals`.

The harness ([`evals/harness.py`](../apps/api/src/atlas_api/evals/harness.py)) **fails** if any case
has uncited claims, retrieves zero sources, or (when required) produces a report with no `[n]`
citations. To run locally:

```bash
cd apps/api
ANTHROPIC_API_KEY=... TAVILY_API_KEY=... \
  DATABASE_URL=postgresql+asyncpg://placeholder/db REDIS_URL=redis://localhost:6379/0 \
  JWT_SECRET=local-eval-secret-32-characters-min \
  uv run python -m atlas_api.evals
```

To watch: open the `Agent eval` workflow run in the Actions tab; a non-zero exit + the printed
failure list (`'<question>': N uncited claim(s)`) indicates a regression in agent quality.

---

## 6. Common failure modes

| Symptom | Likely cause | Action |
|---|---|---|
| Runs stuck in `queued`, never start | No worker running / KEDA didn't scale up | Check `kubectl -n atlas get scaledobject,deploy/atlas-worker`; verify Redis reachable and `arq:queue` has entries; check KEDA `activationLagThreshold` |
| `429` / Claude `overloaded` / Tavily rate limit | Provider rate limits | Back off; lower concurrency (`max_subquestions`, `max_sources_per_q`); workers degrade per-search (one failed search doesn't abort the run). Watch per-provider cost meters |
| Reports come back `truncated` or thin | Per-run token budget hit, or thin/conflicting evidence | Expected guardrail behavior — budget-kill yields a partial report, never a silent spin. Tune `perRunTokenBudget` in `values.yaml` |
| Model **refuses** / injection note in report | A fetched page tried prompt injection | Working as designed: web content is treated as untrusted data; the report notes the injection attempt. See [threat model](threat-model.md) LLM01 |
| `FATAL: too many connections` on RDS | DB connection exhaustion at max KEDA replicas | Ensure traffic goes through **PgBouncer** (transaction mode), `NullPool` + asyncpg `statement_cache_size=0`; size PgBouncer pool vs RDS `max_connections`; cap worker `max_jobs` (default 10) and KEDA `maxReplicaCount` |
| SSE connection drops / no live updates | Proxy buffering the stream | Confirm `Cache-Control: no-cache` + `X-Accel-Buffering: no`; ALB `idle_timeout` 300s; the Cloudflare SSE route must stream, not buffer. Heartbeat comments should appear ~every 15s |
| Reconnect loses events | Past Redis Stream retention (`maxlen ~2000`) | Client should send `Last-Event-ID`; gaps older than retention replay from persisted `run_steps`. Increase stream `maxlen` if reconnect gaps are large |
| `401 Invalid token` after logout / refresh reuse | jti on deny-list, or refresh reuse detected (family revoked) | Expected: logout revokes via Redis jti deny-list; a reused refresh token revokes the whole token family. Re-login |
| Helm upgrade hangs / aborts | `--atomic --wait` failing readiness, or migration hook failed | Check migration Job logs (`kubectl -n atlas logs job/<migration>`); `--atomic` auto-rolls-back; fix migration and re-run |
| `terraform apply` lock error | Concurrent run holding the S3 native lock | Wait, or `terraform force-unlock <id>` only if certain no other apply is running |
