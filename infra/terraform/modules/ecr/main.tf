# ---------------------------------------------------------------------------
# ECR: one repository per service (api/worker/web) with tag immutability
# (deploy-by-digest, §13), scan-on-push, and a lifecycle policy that expires
# untagged layers and caps tagged history. §10.
# ---------------------------------------------------------------------------

# KMS encryption at rest for the repositories (AVD-AWS-0033). A dedicated CMK is
# created unless the caller supplies an existing one via kms_key_arn.
resource "aws_kms_key" "ecr" {
  count = var.kms_key_arn == null ? 1 : 0

  description             = "${var.name_prefix} ECR repository encryption CMK"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-ecr-cmk"
  })
}

resource "aws_kms_alias" "ecr" {
  count = var.kms_key_arn == null ? 1 : 0

  name          = "alias/${var.name_prefix}-ecr"
  target_key_id = aws_kms_key.ecr[0].key_id
}

locals {
  ecr_kms_key_arn = var.kms_key_arn != null ? var.kms_key_arn : aws_kms_key.ecr[0].arn
}

resource "aws_ecr_repository" "this" {
  for_each = toset(var.repositories)

  name                 = "${var.name_prefix}/${each.value}"
  image_tag_mutability = var.image_tag_mutability
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = local.ecr_kms_key_arn
  }

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}/${each.value}"
    Service = each.value
  })
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than ${var.untagged_expire_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_expire_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the most recent ${var.tagged_keep_count} tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "sha-", "main-", "release-"]
          countType     = "imageCountMoreThan"
          countNumber   = var.tagged_keep_count
        }
        action = { type = "expire" }
      },
    ]
  })
}
