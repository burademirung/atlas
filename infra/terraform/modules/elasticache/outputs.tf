output "replication_group_id" {
  description = "ElastiCache replication group ID."
  value       = aws_elasticache_replication_group.this.id
}

output "primary_endpoint_address" {
  description = "Primary endpoint address (writes / arq + Stream XADD)."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "reader_endpoint_address" {
  description = "Reader endpoint address (replica reads). Empty when single-node."
  value       = aws_elasticache_replication_group.this.reader_endpoint_address
}

output "port" {
  description = "Redis port."
  value       = aws_elasticache_replication_group.this.port
}

output "security_group_id" {
  description = "Security group attached to the replication group."
  value       = aws_security_group.redis.id
}

output "kms_key_arn" {
  description = "ARN of the CMK encrypting the cache + AUTH secret."
  value       = aws_kms_key.redis.arn
}

output "auth_secret_arn" {
  description = "Secrets Manager ARN holding the AUTH token JSON. Grant read to the api/worker Pod Identity roles."
  value       = aws_secretsmanager_secret.auth.arn
}
