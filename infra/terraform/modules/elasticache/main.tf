# ---------------------------------------------------------------------------
# ElastiCache for Redis: the arq queue + per-run Redis Streams backbone (§3).
# At-rest (CMK) + in-transit encryption, an AUTH token generated and stored in
# Secrets Manager, optional Multi-AZ + automatic failover (prod), private
# subnets, ingress 6379 from the EKS node SG only.
# ---------------------------------------------------------------------------

# ------------------------------ KMS CMK ------------------------------------

resource "aws_kms_key" "redis" {
  description             = "${var.name_prefix} ElastiCache encryption CMK"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-cmk"
  })
}

resource "aws_kms_alias" "redis" {
  name          = "alias/${var.name_prefix}-redis"
  target_key_id = aws_kms_key.redis.key_id
}

# ------------------------------ AUTH token ---------------------------------
# Redis AUTH tokens must be 16-128 chars and exclude several specials.

resource "random_password" "auth" {
  length           = 64
  special          = true
  override_special = "!&#$^<>-"
}

resource "aws_secretsmanager_secret" "auth" {
  name        = "${var.name_prefix}/redis/auth"
  description = "${var.name_prefix} ElastiCache Redis AUTH token"
  kms_key_id  = aws_kms_key.redis.arn

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "auth" {
  secret_id = aws_secretsmanager_secret.auth.id
  secret_string = jsonencode({
    auth_token = random_password.auth.result
    host       = aws_elasticache_replication_group.this.primary_endpoint_address
    port       = aws_elasticache_replication_group.this.port
    tls        = true
  })
}

# ------------------------------ Networking ---------------------------------

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-subnet-group"
  })
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Redis access for ${var.name_prefix}; ingress 6379 from the EKS node SG only"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_nodes" {
  for_each = toset(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.redis.id
  description                  = "Redis from EKS nodes"
  referenced_security_group_id = each.value
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}

# ---------------------------- Parameter group ------------------------------

resource "aws_elasticache_parameter_group" "this" {
  name   = "${var.name_prefix}-redis"
  family = "redis${split(".", var.engine_version)[0]}"

  # Streams are unbounded by default; the app trims with XADD MAXLEN, but cap
  # eviction to noeviction so the queue never silently drops jobs/streams.
  parameter {
    name  = "maxmemory-policy"
    value = "noeviction"
  }

  tags = var.tags
}

# ---------------------------- Replication group ----------------------------

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "${var.name_prefix} Redis (arq queue + per-run Streams)"

  engine         = "redis"
  engine_version = var.engine_version
  node_type      = var.node_type
  port           = 6379

  num_cache_clusters         = var.num_cache_clusters
  multi_az_enabled           = var.multi_az_enabled
  automatic_failover_enabled = var.automatic_failover_enabled

  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = [aws_security_group.redis.id]
  parameter_group_name = aws_elasticache_parameter_group.this.name

  # Encryption everywhere (§11.5).
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.redis.arn
  transit_encryption_enabled = true
  auth_token                 = random_password.auth.result
  auth_token_update_strategy = "ROTATE"

  snapshot_retention_limit = var.snapshot_retention_limit
  snapshot_window          = var.snapshot_retention_limit > 0 ? var.snapshot_window : null
  maintenance_window       = var.maintenance_window

  auto_minor_version_upgrade = true
  apply_immediately          = var.apply_immediately

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis"
  })
}
