variable "name_prefix" {
  description = "Prefix for all resource names, e.g. \"atlas-dev\"."
  type        = string
}

variable "cidr_block" {
  description = "CIDR block for the VPC. Must be large enough to carve 3 public + 3 private /20s."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.cidr_block, 0))
    error_message = "cidr_block must be a valid IPv4 CIDR."
  }
}

variable "az_count" {
  description = "Number of Availability Zones to span. The design assumes 3."
  type        = number
  default     = 3

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3."
  }
}

variable "single_nat_gateway" {
  description = "When true, route all private subnets through ONE NAT gateway (dev cost saver). When false, one NAT per AZ (prod HA)."
  type        = bool
  default     = false
}

variable "cluster_name" {
  description = "EKS cluster name these subnets belong to; used for the kubernetes.io/cluster discovery tag."
  type        = string
}

variable "region" {
  description = "AWS region (used to build VPC endpoint service names)."
  type        = string
}

variable "enable_flow_logs" {
  description = "Emit VPC flow logs to CloudWatch Logs (recommended in prod for egress/SSRF forensics per §11.2)."
  type        = bool
  default     = false
}

variable "flow_log_retention_days" {
  description = "Retention for the VPC flow log group when enable_flow_logs is true."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module."
  type        = map(string)
  default     = {}
}
