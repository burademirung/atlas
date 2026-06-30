variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes control-plane version, e.g. \"1.31\"."
  type        = string
  default     = "1.31"
}

variable "subnet_ids" {
  description = "Subnet IDs for the control plane ENIs and node group (private subnets)."
  type        = list(string)
}

variable "endpoint_public_access" {
  description = "Allow the EKS API server to be reachable from the public internet. Kept configurable because CI/operators may need it, but it only takes effect when cluster_public_access_cidrs is non-empty. Private access is always enabled."
  type        = bool
  default     = true
}

variable "cluster_public_access_cidrs" {
  description = "Explicit CIDR allow-list for the public API endpoint. Default [] means private-only (no public endpoint). Set a tight list (office/VPN/CI egress) to opt in — never 0.0.0.0/0."
  type        = list(string)
  default     = []

  validation {
    condition     = !contains(var.cluster_public_access_cidrs, "0.0.0.0/0")
    error_message = "cluster_public_access_cidrs must not contain 0.0.0.0/0; restrict the EKS public endpoint to known CIDRs."
  }
}

variable "enabled_cluster_log_types" {
  description = "Control-plane log types shipped to CloudWatch."
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

variable "node_instance_types" {
  description = "Instance types for the system managed node group."
  type        = list(string)
  default     = ["t3.large"]
}

variable "node_capacity_type" {
  description = "Capacity type for the system node group: ON_DEMAND or SPOT. Keep system add-ons ON_DEMAND; burst workers use Spot via Karpenter (out of module scope)."
  type        = string
  default     = "ON_DEMAND"

  validation {
    condition     = contains(["ON_DEMAND", "SPOT"], var.node_capacity_type)
    error_message = "node_capacity_type must be ON_DEMAND or SPOT."
  }
}

variable "node_desired_size" {
  description = "Desired node count for the system node group."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum node count for the system node group."
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum node count for the system node group."
  type        = number
  default     = 3
}

variable "node_disk_size" {
  description = "EBS root volume size (GiB) for nodes."
  type        = number
  default     = 50
}

variable "addon_versions" {
  description = "Optional explicit versions for managed add-ons keyed by addon name. Omit an entry to let EKS pick the default for the cluster version."
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Additional tags merged onto every resource in this module."
  type        = map(string)
  default     = {}
}
