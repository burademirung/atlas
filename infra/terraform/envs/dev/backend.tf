terraform {
  # Remote state in S3 with NATIVE locking (use_lockfile) — no DynamoDB table.
  # The state bucket must already exist, be versioned + SSE-KMS encrypted, and
  # have public access blocked (create it once out-of-band before `init`).
  #
  # Edit bucket/region to point at YOUR state bucket. The key is env-scoped so
  # dev and prod never share state.
  backend "s3" {
    bucket       = "atlas-tfstate-CHANGEME"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
