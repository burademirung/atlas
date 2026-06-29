output "role_arns" {
  description = "Map of workload (api/worker) -> IAM role ARN bound via Pod Identity."
  value       = { for k, role in aws_iam_role.workload : k => role.arn }
}

output "api_role_arn" {
  description = "IAM role ARN for the API workload."
  value       = aws_iam_role.workload["api"].arn
}

output "worker_role_arn" {
  description = "IAM role ARN for the worker workload."
  value       = aws_iam_role.workload["worker"].arn
}

output "pod_identity_association_ids" {
  description = "Map of workload -> Pod Identity association ID."
  value       = { for k, assoc in aws_eks_pod_identity_association.workload : k => assoc.association_id }
}
