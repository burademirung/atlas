# ADR 0005 — Terraform: separate root config + state per environment

**Status:** Accepted · 2026-06-29

## Context

Atlas has `dev` and `prod` environments with materially different shapes (single NAT vs per-AZ,
`t4g.micro` vs `r6g.large`, single-AZ vs Multi-AZ, deletion protection off vs on). We needed an
environment-separation strategy that:

- keeps a mistake in `dev` from ever touching `prod` state,
- lets the two environments diverge in size/HA without conditional sprawl,
- and uses a state-locking mechanism that is current (not deprecated).

Two common anti-patterns to avoid: using **Terraform workspaces** to model environments (they share
one backend/state lineage and one set of root variables — easy to apply to the wrong env), and using
a **DynamoDB lock table** (now superseded by S3 native locking).

## Decision

Use a **separate root configuration and separate state per environment** under
[`infra/terraform/envs/{dev,prod}`](../../infra/terraform/), each composing the same reusable
`modules/` (network, eks, rds, elasticache, ecr, s3, iam, cloudflare). State lives in an **S3 backend
with native locking** (`use_lockfile = true`), **not** DynamoDB. Terraform **workspaces are
deliberately not used** for environment separation. `.terraform.lock.hcl` is committed per env root.

The deploy model is **operator-applied**: `apply` is a deliberate human step;
[`.github/workflows/terraform.yml`](../../.github/workflows/terraform.yml) runs `fmt`/`validate`/Trivy/
Checkov on PRs and a gated read-only `plan` per env on `main`, but never auto-applies.

## Consequences

- **+** **Blast-radius isolation:** `dev` and `prod` have independent state files and backends; an
  errant `apply` in one cannot corrupt the other.
- **+** Environments diverge cleanly via their own `main.tf` + `tfvars` (single NAT vs per-AZ, etc.)
  while sharing module code.
- **+** S3 native locking removes the deprecated DynamoDB lock table — fewer moving parts.
- **+** CI validates both envs in a matrix; humans own `apply`, fitting the operator-applied model
  (ADR 0001).
- **−** Some **duplication** across env roots (provider/backend/variable wiring) versus a single
  workspace-driven root.
- **−** Requires a **pre-existing state bucket per account** (Terraform doesn't bootstrap its own
  backend) — a documented one-time setup step.
- **−** Cross-environment changes (e.g. a module signature change) must be applied to each env
  separately.
