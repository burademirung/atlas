output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (one per AZ)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets (one per AZ). RDS, ElastiCache, and EKS workloads live here."
  value       = aws_subnet.private[*].id
}

output "availability_zones" {
  description = "AZs the network spans."
  value       = local.azs
}

output "nat_gateway_ids" {
  description = "IDs of the NAT gateways."
  value       = aws_nat_gateway.this[*].id
}

output "vpc_endpoint_s3_id" {
  description = "ID of the S3 gateway VPC endpoint (useful for bucket policies that restrict to the endpoint)."
  value       = aws_vpc_endpoint.s3.id
}
