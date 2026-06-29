# Canonical provider + Terraform version constraints for the Atlas project.
#
# This file is the single source of truth for the versions used across every
# root module (envs/dev, envs/prod) and every child module. Each env root and
# child module re-declares the providers it actually consumes (Terraform
# requires `required_providers` to be declared where a provider is used so it
# can be passed explicitly), but the version pins MUST stay in lockstep with
# the constraints below. When bumping a provider, bump it here and in every
# `versions.tf` that mirrors it, then regenerate the committed
# `.terraform.lock.hcl` in each env root with `terraform providers lock`.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
