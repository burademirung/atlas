# ===========================================================================
# Atlas — prod environment root.
#
# prod profile: NAT per-AZ, larger instances, multi_az=true,
# deletion_protection=true, automatic failover. Separate state from dev.
# ===========================================================================

locals {
  name_prefix  = "${var.project}-${var.environment}"
  cluster_name = "${var.project}-${var.environment}"

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

module "network" {
  source = "../../modules/network"

  name_prefix        = local.name_prefix
  cidr_block         = var.vpc_cidr
  az_count           = 3
  single_nat_gateway = false # one NAT per AZ for HA
  cluster_name       = local.cluster_name
  region             = var.region
  enable_flow_logs   = true # forensics for egress/SSRF (§11.2)

  tags = local.tags
}

module "eks" {
  source = "../../modules/eks"

  cluster_name       = local.cluster_name
  kubernetes_version = var.kubernetes_version
  subnet_ids         = module.network.private_subnet_ids

  endpoint_public_access       = true
  endpoint_public_access_cidrs = var.eks_public_access_cidrs

  node_instance_types = ["m6i.large"]
  node_capacity_type  = "ON_DEMAND"
  node_desired_size   = 3
  node_min_size       = 2
  node_max_size       = 6
  node_disk_size      = 100

  tags = local.tags
}

module "ecr" {
  source = "../../modules/ecr"

  name_prefix          = var.project # repos are env-agnostic: atlas/api, atlas/worker, atlas/web
  image_tag_mutability = "IMMUTABLE"
  scan_on_push         = true

  tags = local.tags
}

module "s3" {
  source = "../../modules/s3"

  name_prefix   = local.name_prefix
  bucket_suffix = "report-exports"
  force_destroy = false # protect prod data

  tags = local.tags
}

module "rds" {
  source = "../../modules/rds"

  name_prefix = local.name_prefix
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids

  allowed_security_group_ids = [module.eks.node_security_group_id]

  instance_class        = "db.r6g.large"
  allocated_storage     = 100
  max_allocated_storage = 1000

  multi_az                = true
  deletion_protection     = true
  skip_final_snapshot     = false
  backup_retention_period = 30

  tags = local.tags
}

module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix = local.name_prefix
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids

  allowed_security_group_ids = [module.eks.node_security_group_id]

  node_type                  = "cache.r6g.large"
  num_cache_clusters         = 2
  multi_az_enabled           = true
  automatic_failover_enabled = true
  snapshot_retention_limit   = 7

  tags = local.tags
}

module "iam" {
  source = "../../modules/iam"

  name_prefix  = local.name_prefix
  cluster_name = module.eks.cluster_name

  export_bucket_arn         = module.s3.bucket_arn
  export_bucket_kms_key_arn = module.s3.kms_key_arn

  secret_arns = concat(
    [module.rds.master_secret_arn, module.elasticache.auth_secret_arn],
    var.additional_secret_arns,
  )

  secret_kms_key_arns = concat(
    [module.rds.kms_key_arn, module.elasticache.kms_key_arn],
    var.additional_secret_kms_key_arns,
  )

  tags = local.tags
}

module "cloudflare" {
  source = "../../modules/cloudflare"

  account_id     = var.cloudflare_account_id
  zone_id        = var.cloudflare_zone_id
  worker_name    = "${local.name_prefix}-web"
  app_hostname   = var.app_hostname
  origin_api_url = var.origin_api_url
}
