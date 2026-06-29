variable "name_prefix" {
  description = "Prefix for resource names, e.g. \"atlas-dev\"."
  type        = string
}

variable "vpc_id" {
  description = "VPC the cache lives in."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for the cache subnet group."
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security group IDs allowed to connect on 6379 (the EKS node SG)."
  type        = list(string)
}

variable "engine_version" {
  description = "Redis engine version."
  type        = string
  default     = "7.1"
}

variable "node_type" {
  description = "Cache node type. dev uses cache.t4g.micro; prod uses cache.r6g.large."
  type        = string
  default     = "cache.t4g.micro"
}

variable "num_cache_clusters" {
  description = "Number of nodes in the replication group (1 = primary only; >=2 enables a replica). Prod uses >=2 for failover."
  type        = number
  default     = 1

  validation {
    condition     = var.num_cache_clusters >= 1 && var.num_cache_clusters <= 6
    error_message = "num_cache_clusters must be between 1 and 6."
  }
}

variable "multi_az_enabled" {
  description = "Spread nodes across AZs. Requires num_cache_clusters >= 2 and automatic_failover. true in prod."
  type        = bool
  default     = false
}

variable "automatic_failover_enabled" {
  description = "Promote a replica automatically on primary failure. Requires num_cache_clusters >= 2. true in prod."
  type        = bool
  default     = false
}

variable "snapshot_retention_limit" {
  description = "Days of automatic snapshots to retain (0 disables; t-class nodes do not support snapshots)."
  type        = number
  default     = 0
}

variable "snapshot_window" {
  description = "Daily snapshot window (UTC) when snapshots are enabled."
  type        = string
  default     = "02:00-03:00"
}

variable "maintenance_window" {
  description = "Weekly maintenance window (UTC)."
  type        = string
  default     = "sun:05:00-sun:06:00"
}

variable "apply_immediately" {
  description = "Apply modifications immediately instead of during the maintenance window."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module."
  type        = map(string)
  default     = {}
}
