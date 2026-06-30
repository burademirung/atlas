variable "name_prefix" {
  description = "Prefix for resource names, e.g. \"atlas-dev\"."
  type        = string
}

variable "vpc_id" {
  description = "VPC the database lives in."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for the DB subnet group."
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security group IDs allowed to connect on 5432 (the EKS node SG). Connections are restricted to these — no CIDR ingress."
  type        = list(string)
}

variable "engine_version" {
  description = "PostgreSQL engine version."
  type        = string
  default     = "16.4"
}

variable "instance_class" {
  description = "RDS instance class. dev uses db.t4g.micro; prod uses db.r6g.large."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Initial gp3 storage in GiB."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Upper bound for gp3 storage autoscaling in GiB. Must be >= allocated_storage."
  type        = number
  default     = 100
}

variable "db_name" {
  description = "Name of the initial database."
  type        = string
  default     = "atlas"
}

variable "master_username" {
  description = "Master username. The password is generated and stored in Secrets Manager."
  type        = string
  default     = "atlas_admin"
}

variable "multi_az" {
  description = "Run a synchronous standby in another AZ. true in prod."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Block accidental deletion (AVD-AWS-0177). Safe default true; dev overrides to false for teardown convenience."
  type        = bool
  default     = true
}

variable "iam_database_authentication_enabled" {
  description = "Enable IAM database authentication (AVD-AWS-0176) so workloads can use short-lived IAM tokens."
  type        = bool
  default     = true
}

variable "backup_retention_period" {
  description = "Days of automated backups to retain."
  type        = number
  default     = 7
}

variable "backup_window" {
  description = "Daily backup window (UTC), e.g. \"03:00-04:00\"."
  type        = string
  default     = "03:00-04:00"
}

variable "maintenance_window" {
  description = "Weekly maintenance window (UTC), e.g. \"sun:04:30-sun:05:30\"."
  type        = string
  default     = "sun:04:30-sun:05:30"
}

variable "performance_insights_enabled" {
  description = "Enable Performance Insights."
  type        = bool
  default     = true
}

variable "monitoring_interval" {
  description = "Enhanced Monitoring granularity in seconds (0 disables). Valid: 0,1,5,10,15,30,60."
  type        = number
  default     = 60
}

variable "skip_final_snapshot" {
  description = "Skip the final snapshot on destroy. true is convenient in dev; keep false in prod."
  type        = bool
  default     = true
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
