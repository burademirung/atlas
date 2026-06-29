output "repository_urls" {
  description = "Map of service name -> repository URL (push/pull target)."
  value       = { for k, repo in aws_ecr_repository.this : k => repo.repository_url }
}

output "repository_arns" {
  description = "Map of service name -> repository ARN."
  value       = { for k, repo in aws_ecr_repository.this : k => repo.arn }
}

output "registry_id" {
  description = "Registry (account) ID hosting the repositories."
  value       = values(aws_ecr_repository.this)[0].registry_id
}
