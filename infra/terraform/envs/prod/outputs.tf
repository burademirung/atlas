output "vpc_id" {
  description = "VPC ID."
  value       = module.network.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = module.network.private_subnet_ids
}

output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint."
  value       = module.eks.cluster_endpoint
}

output "cluster_oidc_provider_arn" {
  description = "OIDC provider ARN (IRSA fallback)."
  value       = module.eks.oidc_provider_arn
}

output "ecr_repository_urls" {
  description = "Map of service -> ECR repo URL."
  value       = module.ecr.repository_urls
}

output "report_bucket" {
  description = "Report-export bucket name."
  value       = module.s3.bucket_id
}

output "rds_address" {
  description = "RDS endpoint address (front with PgBouncer)."
  value       = module.rds.db_address
}

output "rds_master_secret_arn" {
  description = "Secrets Manager ARN for the RDS master credentials."
  value       = module.rds.master_secret_arn
}

output "redis_primary_endpoint" {
  description = "Redis primary endpoint."
  value       = module.elasticache.primary_endpoint_address
}

output "redis_auth_secret_arn" {
  description = "Secrets Manager ARN for the Redis AUTH token."
  value       = module.elasticache.auth_secret_arn
}

output "api_pod_identity_role_arn" {
  description = "IAM role ARN bound to the API service account via Pod Identity."
  value       = module.iam.api_role_arn
}

output "worker_pod_identity_role_arn" {
  description = "IAM role ARN bound to the worker service account via Pod Identity."
  value       = module.iam.worker_role_arn
}

output "app_url" {
  description = "Public app hostname served by the Cloudflare Worker."
  value       = "https://${module.cloudflare.app_hostname}"
}
