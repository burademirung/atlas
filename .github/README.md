# Atlas CI/CD

GitHub Actions pipeline for the Deep-Research Studio (Atlas) monorepo. Design
intent: see `docs/superpowers/specs/2026-06-29-deep-research-studio-design.md` §10.

## Principles applied to every workflow

- **Least privilege** — top-level `permissions: {}`; each job re-grants only the
  scopes it needs (`contents: read`, `id-token: write`, `security-events: write`).
- **Pinned actions** — every third-party action is pinned to a full commit SHA
  with a trailing `# vX.Y.Z` comment. Dependabot (`github-actions` ecosystem)
  bumps both the SHA and the comment.
- **Concurrency** — PR CI is `cancel-in-progress: true` (save runner minutes);
  deploys (`cd`, `pages`, terraform `plan`) are serialized with
  `cancel-in-progress: false` so two never race for the same target.
- **Keyless cloud auth** — AWS access uses **GitHub OIDC** (`configure-aws-credentials`
  assuming an IAM role). There are **no long-lived AWS keys** anywhere. Cloudflare
  has no OIDC for wrangler yet, so it uses a single **scoped, rotated** API token.

> ⚠️ **Action SHAs are representative pins.** They map to real, current actions
> at the annotated versions, but verify and re-pin them in your repo with
> `pin-github-action` (or let the `github-actions` Dependabot config do it)
> before relying on them in production.

## Workflows

| File | Trigger | What it does |
|---|---|---|
| `ci.yml` | PR + push to main | **api**: `uv sync` → ruff (lint+format) → mypy `src` (strict) → pytest w/ coverage (testcontainers Postgres/Redis) → upload coverage. **web**: `npm ci` → `tsc --noEmit`. **security**: Trivy fs + IaC config gates (fail on CRITICAL/HIGH), SARIF upload, gitleaks secret scan. |
| `codeql.yml` | PR + push to main + weekly | CodeQL `security-extended` over a matrix of `python` and `javascript-typescript`. |
| `cd.yml` | push to main + `v*` tags | OIDC → AWS. Build/sign (cosign keyless)/SBOM/push **api, worker, web** images to ECR; deploy via `helm upgrade --install` against EKS. Pins images **by digest**. Gated by the `production` Environment (required reviewers). Serialized. |
| `pages.yml` | push to main (`apps/cloudflare/**`) + manual | `npm ci` → `tsc --noEmit` → `wrangler deploy` of the Worker + SPA assets, using a scoped `CLOUDFLARE_API_TOKEN`. |
| `terraform.yml` | PR / push touching `infra/terraform/**` | **PR**: `fmt -check`, `init -backend=false`, `validate`, Trivy config scan + Checkov policy gate (matrix dev/prod). **push to main**: OIDC → read-only AWS role, gated `plan` per env (`infra-plan` Environment). Apply stays manual. |
| `dependabot.yml` | weekly | Updates pip (`apps/api`), npm (`apps/cloudflare`), github-actions (`/`), terraform (`infra/terraform`), docker (`apps/api`). |

## Required GitHub Environments

Create these under **Settings → Environments** with **required reviewers**:

| Environment | Used by | Protect with |
|---|---|---|
| `production` | `cd.yml` (deploy) | Required reviewers; restrict to `main` + `v*` tags. |
| `cloudflare-production` | `pages.yml` | Required reviewers (optional); holds `CLOUDFLARE_API_TOKEN`. |
| `infra-plan` | `terraform.yml` (plan) | Required reviewers; read-only role only. |

## Required repository / environment configuration

### Variables (`vars.*`, non-secret)

| Name | Example | Used by |
|---|---|---|
| `AWS_REGION` | `eu-west-1` | cd, terraform |
| `ECR_REGISTRY` | `123456789012.dkr.ecr.eu-west-1.amazonaws.com` | cd |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/atlas-gha-deploy` | cd |
| `AWS_TF_PLAN_ROLE_ARN` | `arn:aws:iam::123456789012:role/atlas-gha-tfplan-ro` | terraform |
| `EKS_CLUSTER_NAME` | `atlas-prod` | cd |
| `APP_URL` | `https://atlas.example.com` | cd (Environment URL) |
| `CLOUDFLARE_ACCOUNT_ID` | `f037e…` | pages |
| `CLOUDFLARE_WORKER_URL` | `https://atlas-research.example.workers.dev` | pages (Environment URL) |

### Secrets (`secrets.*`)

| Name | Notes |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Scoped token: *Workers Scripts: Edit* (+ KV/D1/account read for the bindings in `wrangler.jsonc`). **Not** a global API key. Rotate regularly. Store on the `cloudflare-production` Environment. |
| `CODECOV_TOKEN` | Optional — only if the commented Codecov step in `ci.yml` is enabled. |

> `GITHUB_TOKEN` is provided automatically; gitleaks uses it for PR annotations.
> No AWS keys are stored — AWS auth is OIDC role assumption only.

## OIDC / AWS IAM setup (one-time)

1. **Create the GitHub OIDC provider** in your AWS account (if not present):
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
2. **Create two roles** with a trust policy scoped to *this* repo (and ideally the
   specific environments/branches), e.g.:
   ```json
   {
     "Effect": "Allow",
     "Principal": { "Federated": "arn:aws:iam::<acct>:oidc-provider/token.actions.githubusercontent.com" },
     "Action": "sts:AssumeRoleWithWebIdentity",
     "Condition": {
       "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
       "StringLike": {
         "token.actions.githubusercontent.com:sub": "repo:<org>/<repo>:*"
       }
     }
   }
   ```
   Tighten `sub` to `...:environment:production` (deploy role) and
   `...:environment:infra-plan` (plan role) once the Environments exist.
   - **`atlas-gha-deploy`** (`AWS_DEPLOY_ROLE_ARN`): ECR push (`ecr:*` on the Atlas
     repos), `eks:DescribeCluster`, and the Kubernetes RBAC binding for Helm.
   - **`atlas-gha-tfplan-ro`** (`AWS_TF_PLAN_ROLE_ARN`): **read-only** + Terraform
     S3 state read and lock (`s3:GetObject/PutObject` on the lock object for
     native `use_lockfile` locking). No mutating cloud permissions — apply is run
     by a human with a separate, stronger role.
3. **ECR repos** (`atlas/api`, `atlas/worker`, `atlas/web`) must exist with **tag
   immutability** enabled (provisioned by `infra/terraform/modules/ecr`).
4. **Cosign keyless** signing uses the same job `id-token` to obtain a Fulcio
   certificate and records to the Rekor transparency log — no key material to manage.

## Conventions & extension points

- Images deploy **by digest** (`@sha256:…`), never by mutable tag — matches the
  immutable-release strategy in spec §13.
- The Helm chart lives at `infra/k8s` (`values.yaml` + templates). `cd.yml` passes
  the freshly-built digests via `--set-string image.<svc>.digest=…`.
- The arq **worker** shares `apps/api/Dockerfile` with the API; only the chart's
  command differs. The **web** image is the in-cluster static origin behind the
  Cloudflare Worker (build it from `apps/cloudflare/Dockerfile`).
- Suggested follow-ups from spec §10 not yet wired here: **nightly Terraform
  drift-detection** plan, **cosign admission verification** in-cluster (reject
  unsigned), and a scheduled **agent-quality eval** harness.
