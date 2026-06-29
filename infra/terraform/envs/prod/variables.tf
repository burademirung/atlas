# ----------------------------- Global ---------------------------------------

variable "project" {
  description = "Project name; stamped on every resource via default_tags."
  type        = string
  default     = "atlas"
}

variable "environment" {
  description = "Environment name; stamped on every resource via default_tags."
  type        = string
  default     = "prod"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

# ------------------------------ EKS -----------------------------------------

variable "kubernetes_version" {
  description = "EKS control-plane version."
  type        = string
  default     = "1.31"
}

variable "eks_public_access_cidrs" {
  description = "CIDRs allowed to reach the public EKS API endpoint. Lock this down in prod."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# --------------------------- Cloudflare -------------------------------------

variable "cloudflare_api_token" {
  description = "Cloudflare API token (Workers + DNS edit). Supply via TF_VAR_cloudflare_api_token; never commit."
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for the app domain."
  type        = string
}

variable "app_hostname" {
  description = "Hostname the app is served on, e.g. \"atlas.example.com\"."
  type        = string
}

variable "origin_api_url" {
  description = "Origin URL the edge Worker proxies to (EKS ingress / LB DNS)."
  type        = string
}

# ------------------------ Application secrets --------------------------------

variable "additional_secret_arns" {
  description = "Extra Secrets Manager ARNs (e.g. app JWT signing key, Tavily/Anthropic API keys) the workloads may read. Create these out-of-band and pass their ARNs here."
  type        = list(string)
  default     = []
}

variable "additional_secret_kms_key_arns" {
  description = "CMK ARNs encrypting the additional secrets above."
  type        = list(string)
  default     = []
}
