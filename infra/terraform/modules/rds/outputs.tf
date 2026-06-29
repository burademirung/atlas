output "db_instance_id" {
  description = "RDS instance identifier."
  value       = aws_db_instance.this.id
}

output "db_instance_arn" {
  description = "RDS instance ARN."
  value       = aws_db_instance.this.arn
}

output "db_address" {
  description = "DNS address of the instance (use PgBouncer in front of this)."
  value       = aws_db_instance.this.address
}

output "db_port" {
  description = "Port the instance listens on."
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Initial database name."
  value       = aws_db_instance.this.db_name
}

output "security_group_id" {
  description = "Security group attached to the instance."
  value       = aws_security_group.db.id
}

output "kms_key_arn" {
  description = "ARN of the CMK encrypting storage + the credentials secret."
  value       = aws_kms_key.rds.arn
}

output "master_secret_arn" {
  description = "Secrets Manager ARN holding the master credentials JSON. Grant read to the api/worker Pod Identity roles."
  value       = aws_secretsmanager_secret.master.arn
}
