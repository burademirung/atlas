variable "name_prefix" {
  description = "Prefix for the bucket name, e.g. \"atlas-dev\"."
  type        = string
}

variable "bucket_suffix" {
  description = "Suffix appended after name_prefix, e.g. \"report-exports\". The final bucket name is <prefix>-<suffix>-<random>."
  type        = string
  default     = "report-exports"
}

variable "force_destroy" {
  description = "Allow Terraform to delete a non-empty bucket. true is convenient in dev; keep false in prod."
  type        = bool
  default     = false
}

variable "noncurrent_version_expiration_days" {
  description = "Expire noncurrent object versions after this many days."
  type        = number
  default     = 30
}

variable "current_version_expiration_days" {
  description = "Expire current report exports after this many days (0 disables; exports are pre-signed + ephemeral). Matches the §11.5 retention policy."
  type        = number
  default     = 90
}

variable "abort_incomplete_multipart_days" {
  description = "Abort incomplete multipart uploads after this many days."
  type        = number
  default     = 7
}

variable "access_log_expiration_days" {
  description = "Expire server access logs in the dedicated log bucket after this many days."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module."
  type        = map(string)
  default     = {}
}
