variable "name_prefix" {
  description = "Prefix for repository names, e.g. \"atlas\". Repos become <prefix>/api, <prefix>/worker, <prefix>/web."
  type        = string
}

variable "repositories" {
  description = "Service names to create repositories for."
  type        = list(string)
  default     = ["api", "worker", "web"]
}

variable "image_tag_mutability" {
  description = "IMMUTABLE (deploy-by-digest, recommended) or MUTABLE."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["IMMUTABLE", "MUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be IMMUTABLE or MUTABLE."
  }
}

variable "scan_on_push" {
  description = "Run a vulnerability scan on every push."
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "Optional existing KMS CMK ARN for repository encryption (AVD-AWS-0033). When null, the module creates a dedicated CMK; repositories are always KMS-encrypted."
  type        = string
  default     = null
}

variable "untagged_expire_days" {
  description = "Expire untagged images older than this many days."
  type        = number
  default     = 14
}

variable "tagged_keep_count" {
  description = "Keep at most this many tagged images per repository."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module."
  type        = map(string)
  default     = {}
}
