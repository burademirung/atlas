output "bucket_id" {
  description = "Name of the report-export bucket."
  value       = aws_s3_bucket.this.id
}

output "bucket_arn" {
  description = "ARN of the bucket. Grant scoped access to the api/worker Pod Identity roles."
  value       = aws_s3_bucket.this.arn
}

output "bucket_domain_name" {
  description = "Regional domain name of the bucket."
  value       = aws_s3_bucket.this.bucket_regional_domain_name
}

output "kms_key_arn" {
  description = "ARN of the CMK encrypting objects. The Pod Identity roles need kms:Decrypt/GenerateDataKey on this."
  value       = aws_kms_key.s3.arn
}
