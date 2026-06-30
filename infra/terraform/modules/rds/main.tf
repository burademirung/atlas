# ---------------------------------------------------------------------------
# RDS PostgreSQL: gp3 with storage autoscaling, CMK encryption, automated
# backups, optional Multi-AZ + deletion protection, a parameter group that
# forces TLS (rds.force_ssl=1), private subnets, and a security group that
# admits 5432 ONLY from the EKS node SG (no CIDR ingress). §10/§11.5.
# ---------------------------------------------------------------------------

data "aws_partition" "current" {}

# ------------------------------ KMS CMK ------------------------------------

resource "aws_kms_key" "rds" {
  description             = "${var.name_prefix} RDS encryption CMK"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-rds-cmk"
  })
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.name_prefix}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# --------------------------- Master password -------------------------------

resource "random_password" "master" {
  length = 32
  # RDS disallows / @ " and spaces in the master password.
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "master" {
  name        = "${var.name_prefix}/rds/master"
  description = "${var.name_prefix} RDS PostgreSQL master credentials"
  kms_key_id  = aws_kms_key.rds.arn

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id = aws_secretsmanager_secret.master.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
    engine   = "postgres"
    host     = aws_db_instance.this.address
    port     = aws_db_instance.this.port
    dbname   = var.db_name
  })
}

# ------------------------------ Networking ---------------------------------

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-db-subnet-group"
  })
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db-sg"
  description = "PostgreSQL access for ${var.name_prefix}; ingress 5432 from the EKS node SG only"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-db-sg"
  })
}

resource "aws_vpc_security_group_ingress_rule" "db_from_nodes" {
  for_each = toset(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL from EKS nodes"
  referenced_security_group_id = each.value
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

# No egress is required for the instance itself; allow return traffic only.
resource "aws_vpc_security_group_egress_rule" "db_none" {
  security_group_id = aws_security_group.db.id
  description       = "No initiated egress; stateful responses only"
  cidr_ipv4         = "127.0.0.1/32"
  ip_protocol       = "tcp"
  from_port         = 5432
  to_port           = 5432
}

# --------------------------- Parameter group -------------------------------

resource "aws_db_parameter_group" "this" {
  name        = "${var.name_prefix}-pg"
  family      = "postgres${split(".", var.engine_version)[0]}"
  description = "${var.name_prefix} PostgreSQL parameters (force TLS)"

  # Reject any non-SSL connection at the server.
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  # Log slow statements (>1s) and connections for auditability (§11.5).
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

# ----------------------- Enhanced Monitoring role --------------------------

data "aws_iam_policy_document" "monitoring_assume" {
  count = var.monitoring_interval > 0 ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0

  name               = "${var.name_prefix}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume[0].json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0

  role       = aws_iam_role.monitoring[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# ------------------------------- Instance ----------------------------------

resource "aws_db_instance" "this" {
  # deletion_protection defaults to true and prod enforces it; atlas-dev
  # deliberately sets it false so the throwaway dev stack can be torn down with
  # `terraform destroy`. Accepting AVD-AWS-0177 / CKV_AWS_293 for that case only.
  #checkov:skip=CKV_AWS_293:dev intentionally disables RDS deletion protection for teardown; prod enforces deletion_protection=true
  identifier = "${var.name_prefix}-pg"

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  # gp3 with autoscaling: storage grows up to max_allocated_storage on demand.
  storage_type          = "gp3"
  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage

  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn

  # Allow IAM-based DB auth alongside the password in Secrets Manager
  # (AVD-AWS-0176): lets workloads use short-lived IAM tokens instead of a
  # long-lived password.
  iam_database_authentication_enabled = var.iam_database_authentication_enabled

  db_name  = var.db_name
  username = var.master_username
  password = random_password.master.result
  port     = 5432

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  parameter_group_name = aws_db_parameter_group.this.name

  backup_retention_period = var.backup_retention_period
  backup_window           = var.backup_window
  maintenance_window      = var.maintenance_window
  copy_tags_to_snapshot   = true

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name_prefix}-pg-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  auto_minor_version_upgrade = true
  apply_immediately          = var.apply_immediately

  performance_insights_enabled    = var.performance_insights_enabled
  performance_insights_kms_key_id = var.performance_insights_enabled ? aws_kms_key.rds.arn : null

  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = var.monitoring_interval > 0 ? aws_iam_role.monitoring[0].arn : null

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-pg"
  })

  lifecycle {
    # The generated final snapshot id embeds a timestamp; ignore so it does not
    # force replacement on every plan.
    ignore_changes = [final_snapshot_identifier]
  }
}
