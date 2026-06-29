# Atlas — Terraform

Infrastructure-as-code for **Atlas** (Deep-Research Studio). This tree provisions the
AWS + Cloudflare footprint described in §10/§11 of the design spec
(`docs/superpowers/specs/2026-06-29-deep-research-studio-design.md`).

The deploy model is **"user applies with their own AWS/Cloudflare credentials."** We ship
runnable, modular HCL; the operator supplies secrets (DB master password is generated, API
keys/tokens are passed at apply time) and runs `plan`/`apply` per environment.

## What this provisions

| Module | Provisions |
|---|---|
| `modules/network` | VPC across 3 AZs, public + private subnets, Internet Gateway, NAT (single in dev / per-AZ in prod), route tables, and VPC endpoints (S3 + DynamoDB gateway; ECR API/DKR, Secrets Manager, STS, CloudWatch Logs interface). Subnets tagged for EKS LB discovery. |
| `modules/eks` | EKS control plane (configurable Kubernetes version), a small managed node group for system add-ons, cluster + node IAM, the **EKS Pod Identity** agent addon, and an OIDC provider for IRSA fallback. |
| `modules/rds` | PostgreSQL (`aws_db_instance`): gp3 with storage autoscaling, KMS CMK encryption, automated backups, optional Multi-AZ + deletion protection, a parameter group forcing TLS (`rds.force_ssl`), private subnets, and a security group allowing 5432 only from the EKS node SG. |
| `modules/elasticache` | Redis replication group: at-rest + in-transit encryption, AUTH token (generated, stored in Secrets Manager), optional Multi-AZ + automatic failover, private subnets. |
| `modules/ecr` | ECR repos for `api`, `worker`, `web` with tag immutability, scan-on-push, and a lifecycle policy. |
| `modules/s3` | Report-export bucket: versioning, SSE-KMS, full public-access block, TLS-only bucket policy, lifecycle rules. |
| `modules/iam` | EKS **Pod Identity** associations for the `api` and `worker` service accounts, scoped least-privilege to the export bucket + the relevant Secrets Manager ARNs. IRSA documented as the fallback. |
| `modules/cloudflare` | Cloudflare Worker (SPA static assets + edge proxy) and a proxied DNS record for the app hostname. |

Remote state lives in an **S3 backend with native locking** (`use_lockfile = true`, *not*
DynamoDB — per the spec, the DynamoDB lock table is deprecated). State is **separate per
environment** (`envs/dev`, `envs/prod`); Terraform workspaces are deliberately **not** used
for environment separation (anti-pattern).

## Layout

```
infra/terraform/
  versions.tf              # canonical version constraints (mirrored into each root/module)
  modules/
    network/  eks/  rds/  elasticache/  ecr/  s3/  iam/  cloudflare/
  envs/
    dev/     # single NAT, smaller instances, multi_az=false, deletion_protection=false
    prod/    # NAT per-AZ, larger instances, multi_az=true, deletion_protection=true
```

Each env root contains `backend.tf`, `providers.tf`, `main.tf`, `variables.tf`,
`outputs.tf`, and a `terraform.tfvars.example`.

## Prerequisites

- Terraform `>= 1.10` (native S3 state locking lands in 1.10).
- AWS credentials with permissions to create the resources above (SSO profile or
  environment credentials). The CD pipeline uses GitHub OIDC, not static keys.
- A Cloudflare API token (Workers + DNS edit) and the target zone/account IDs.
- A pre-existing **state bucket** per account, versioned + SSE-KMS + public-access-blocked.
  Terraform does not bootstrap its own backend; create it once out-of-band (or with a
  separate `bootstrap` root) before the first `init`.

## Applying per environment

```bash
cd infra/terraform/envs/dev      # or envs/prod

# 1. Copy the example tfvars and fill in real values (no secrets are committed).
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars

# 2. Edit backend.tf so the bucket/key/region point at YOUR state bucket, then:
terraform init

# 3. Review and apply.
terraform plan  -out tfplan
terraform apply tfplan
```

Provide the Cloudflare token via environment (never in tfvars):

```bash
export TF_VAR_cloudflare_api_token=...   # CLOUDFLARE_API_TOKEN also works for the provider
```

The generated RDS master password and Redis AUTH token are written to AWS Secrets Manager —
read them from there, they are marked `sensitive` and never printed.

### dev vs prod

| | dev | prod |
|---|---|---|
| NAT gateways | 1 (shared) | 1 per AZ |
| RDS instance | `db.t4g.micro` | `db.r6g.large` |
| RDS Multi-AZ | `false` | `true` |
| RDS deletion protection | `false` | `true` |
| ElastiCache nodes | 1, `cache.t4g.micro`, no failover | 2, `cache.r6g.large`, Multi-AZ failover |
| EKS node group | 1–3 × `t3.large` | 2–6 × `m6i.large` |

## Conventions

- `default_tags` on the AWS provider stamp every resource (`Project`, `Environment`,
  `ManagedBy`). Modules add resource-specific tags on top.
- No account IDs, secrets, hostnames, or zone IDs are hardcoded — everything is a variable.
- `.terraform.lock.hcl` is committed per env root (run `terraform providers lock` for the
  platforms your CI/operators use, e.g. `linux_amd64`, `darwin_arm64`).
