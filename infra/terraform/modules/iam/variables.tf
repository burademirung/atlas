variable "name_prefix" {
  description = "Prefix for IAM role names, e.g. \"atlas-dev\"."
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name the Pod Identity associations bind to."
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace the api/worker service accounts live in."
  type        = string
  default     = "atlas"
}

variable "api_service_account" {
  description = "Service account name used by the API Deployment."
  type        = string
  default     = "atlas-api"
}

variable "worker_service_account" {
  description = "Service account name used by the worker Deployment."
  type        = string
  default     = "atlas-worker"
}

variable "export_bucket_arn" {
  description = "ARN of the S3 report-export bucket the workloads read/write."
  type        = string
}

variable "export_bucket_kms_key_arn" {
  description = "ARN of the CMK encrypting the export bucket (needed for KMS Decrypt/GenerateDataKey)."
  type        = string
}

variable "secret_arns" {
  description = "Secrets Manager ARNs the workloads may read (RDS master, Redis AUTH, app/provider keys)."
  type        = list(string)
}

variable "secret_kms_key_arns" {
  description = "CMK ARNs that encrypt the secrets above (for kms:Decrypt on GetSecretValue)."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module."
  type        = map(string)
  default     = {}
}
