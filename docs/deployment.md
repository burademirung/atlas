# Deployment

> How each edition of Firstline / Atlas deploys. For day-2 operations (secrets, migrations,
> rollback, failure modes) see the [runbook](runbook.md); this doc is the deploy path itself.

## Table of contents

- [Two deploy targets](#two-deploy-targets)
- [Live (Cloudflare) edition](#live-cloudflare-edition)
- [Production edition — infrastructure (Terraform)](#production-edition--infrastructure-terraform)
- [Production edition — application (Helm via CD)](#production-edition--application-helm-via-cd)
- [CI/CD workflow reference](#cicd-workflow-reference)

## Two deploy targets

| | Live (Cloudflare) | Production (AWS) |
|---|---|---|
| Artifact | One Worker + SPA assets | 3 container images (`api`, `worker`, `web`) + Helm release |
| Tooling | `wrangler` | Terraform (infra) + Helm (app) |
| Pipeline | [`pages.yml`](../.github/workflows/pages.yml) | [`terraform.yml`](../.github/workflows/terraform.yml) + [`cd.yml`](../.github/workflows/cd.yml) |
| Auth to cloud | Scoped Cloudflare API token | GitHub **OIDC → assume role** (no static keys) |

## Live (Cloudflare) edition

Code: [`apps/cloudflare/`](../apps/cloudflare/). Deployed at
<https://atlas-research.burademirung.workers.dev>.

**Automated (preferred):** push to `main` touching `apps/cloudflare/**` triggers `pages.yml`, which
type-checks (`tsc --noEmit`) and runs `wrangler deploy` using a scoped `CLOUDFLARE_API_TOKEN`
secret + `CLOUDFLARE_ACCOUNT_ID` variable, gated by the `cloudflare-production` GitHub Environment.

**Manual:**

```bash
cd apps/cloudflare
npm ci
npx wrangler secret put ANTHROPIC_API_KEY          # one-time, per environment
npx wrangler d1 migrations apply atlas-research      # apply D1 schema (add --local for local)
npx wrangler deploy
```

[`wrangler.jsonc`](../apps/cloudflare/wrangler.jsonc) binds the D1 database (`DB`), static assets
(`ASSETS`, SPA fallback via `not_found_handling: single-page-application`, with `/api/*` routed to
the Worker first), and a Workers AI binding (`AI`). Optional `TURNSTILE_SECRET` / `TURNSTILE_SITEKEY`
secrets enable bot verification. D1 is forward-only — see [rollback](runbook.md#4-rollback).

## Production edition — infrastructure (Terraform)

Code: [`infra/terraform/`](../infra/terraform/). Pipeline: [`terraform.yml`](../.github/workflows/terraform.yml).

The deploy model is **"the operator applies with their own AWS/Cloudflare credentials."** CI runs
`fmt`/`validate`/`plan` on PRs and a gated, read-only `plan` on `main`; **`apply` is deliberately a
human-run step.**

**Prerequisites:** Terraform ≥ 1.10 (native S3 state locking), a pre-existing versioned + SSE-KMS
state bucket per account, AWS credentials, and a Cloudflare API token + zone/account IDs.

```bash
cd infra/terraform/envs/dev        # or envs/prod — separate root config + state per env
cp terraform.tfvars.example terraform.tfvars && $EDITOR terraform.tfvars
$EDITOR backend.tf                 # point bucket/key/region at YOUR state bucket
export TF_VAR_cloudflare_api_token=...   # never in tfvars
terraform init
terraform plan  -out tfplan
terraform apply tfplan
```

This provisions VPC + endpoints, EKS (Pod Identity), RDS PostgreSQL, ElastiCache Redis, S3, ECR,
IAM, and the Cloudflare Worker/DNS. The RDS master password and Redis AUTH token are generated and
written to **AWS Secrets Manager**. Module map and dev-vs-prod table:
[`infra/terraform/README.md`](../infra/terraform/README.md).

**Cluster add-ons** (installed once, separate lifecycle from the app — *not* part of the Atlas
chart): KEDA, External Secrets Operator, AWS Load Balancer Controller, a NetworkPolicy-enforcing
CNI, and metrics-server. See [`infra/k8s/README.md`](../infra/k8s/README.md).

## Production edition — application (Helm via CD)

Code: [`infra/k8s/atlas/`](../infra/k8s/atlas/). Pipeline: [`cd.yml`](../.github/workflows/cd.yml).

**Automated (preferred):** a push to `main` or a `v*` tag triggers `CD`, which:

1. Builds 3 images (`api`, `worker`, `web`) — `api` and `worker` share `apps/api/Dockerfile`; `web`
   builds from `apps/web/Dockerfile`.
2. Signs them with **cosign** (keyless OIDC) and attaches an **SBOM** (syft) + SLSA provenance.
3. Pushes to **ECR addressed by digest** (tag immutability).
4. Runs `helm upgrade --install atlas …` pinning every image **by digest**.

The deploy job runs inside the `production` GitHub Environment (required reviewers), so a human
approves before anything reaches the cluster. AWS access is GitHub OIDC.

**Manual Helm:**

```bash
aws eks update-kubeconfig --name <cluster> --region <region>

# Enforce the Restricted Pod Security Standard on the namespace:
kubectl create namespace atlas --dry-run=client -o yaml | kubectl apply -f -
kubectl label --overwrite namespace atlas \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/audit=restricted

helm upgrade --install atlas infra/k8s/atlas \
  --namespace atlas \
  --values infra/k8s/atlas/values.yaml \
  --atomic --wait --timeout 10m
kubectl -n atlas rollout status deployment/atlas-api --timeout=5m
```

The Alembic migration runs automatically as a Helm **pre-upgrade hook Job** before the new pods
roll. On a brand-new install there is an ordering caveat between the migration hook and the
ExternalSecret — see [`infra/k8s/atlas/README.md`](../infra/k8s/atlas/README.md#first-install-ordering-caveat-migrations--externalsecret).
Use **expand-contract / backward-compatible** migrations only.

## CI/CD workflow reference

All workflows apply least privilege (top-level `permissions: {}`), pin third-party actions to a
full commit SHA, and use OIDC for AWS. Full reference: [`.github/README.md`](../.github/README.md).

| Workflow | Trigger | Does |
|---|---|---|
| [`ci.yml`](../.github/workflows/ci.yml) | PR + push to main | api: ruff → mypy → pytest; web: `tsc`; security: Trivy + gitleaks |
| [`codeql.yml`](../.github/workflows/codeql.yml) | PR + push + weekly | CodeQL `security-extended` (Python + JS/TS) |
| [`cd.yml`](../.github/workflows/cd.yml) | push to main + `v*` tags | OIDC → AWS; build/sign/SBOM → ECR by digest → `helm upgrade` on EKS (gated `production`) |
| [`pages.yml`](../.github/workflows/pages.yml) | push to main (`apps/cloudflare/**`) + manual | `tsc` → `wrangler deploy` (gated `cloudflare-production`) |
| [`terraform.yml`](../.github/workflows/terraform.yml) | PR / push (`infra/terraform/**`) | fmt/validate/plan + Trivy/Checkov; gated read-only `plan` on main |
| [`eval.yml`](../.github/workflows/eval.yml) | weekly + manual | live agent-quality eval (`python -m atlas_api.evals`) |

Required GitHub Environments: `production` (deploy), `cloudflare-production` (Worker), `infra-plan`
(Terraform plan) — all with required reviewers. The one-time OIDC/IAM setup is documented in
[`.github/README.md`](../.github/README.md#oidc--aws-iam-setup-one-time).
</content>
