# ===========================================================================
# Atlas — dev environment root.
#
# dev profile: single NAT, smaller instances, multi_az=false,
# deletion_protection=false. Separate state from prod (see backend.tf).
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
  single_nat_gateway = true # dev cost saver
  cluster_name       = local.cluster_name
  region             = var.region
  enable_flow_logs   = true # VPC flow logs in every env (AVD-AWS-0178)

  tags = local.tags
}

module "eks" {
  source = "../../modules/eks"

  cluster_name       = local.cluster_name
  kubernetes_version = var.kubernetes_version
  subnet_ids         = module.network.private_subnet_ids

  endpoint_public_access      = true
  cluster_public_access_cidrs = var.eks_public_access_cidrs

  node_instance_types = ["t3.large"]
  node_capacity_type  = "ON_DEMAND"
  node_desired_size   = 2
  node_min_size       = 1
  node_max_size       = 3
  node_disk_size      = 50

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
  force_destroy = true # dev convenience

  tags = local.tags
}

module "rds" {
  source = "../../modules/rds"

  name_prefix = local.name_prefix
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids

  allowed_security_group_ids = [module.eks.node_security_group_id]

  instance_class        = "db.t4g.micro"
  allocated_storage     = 20
  max_allocated_storage = 100

  multi_az                = false
  deletion_protection     = false
  skip_final_snapshot     = true
  backup_retention_period = 7

  tags = local.tags
}

module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix = local.name_prefix
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids

  allowed_security_group_ids = [module.eks.node_security_group_id]

  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  multi_az_enabled           = false
  automatic_failover_enabled = false

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
