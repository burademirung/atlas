# ---------------------------------------------------------------------------
# S3: report-export bucket. Versioned, SSE-KMS (dedicated CMK), full public
# access block, TLS-only bucket policy, and lifecycle rules. Objects are served
# to users via short-lived pre-signed URLs only — never public (§11.3/§11.5).
# ---------------------------------------------------------------------------

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_kms_key" "s3" {
  description             = "${var.name_prefix} S3 report-export encryption CMK"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-s3-cmk"
  })
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${var.name_prefix}-${var.bucket_suffix}"
  target_key_id = aws_kms_key.s3.key_id
}

resource "aws_s3_bucket" "this" {
  bucket = "${var.name_prefix}-${var.bucket_suffix}-${random_id.suffix.hex}"

  force_destroy = var.force_destroy

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-${var.bucket_suffix}"
  })
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    object_ownership = "BucketOwnerEnforced" # disables ACLs entirely
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true # reduces KMS request cost
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {} # whole bucket

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = var.abort_incomplete_multipart_days
    }
  }

  dynamic "rule" {
    for_each = var.current_version_expiration_days > 0 ? [1] : []

    content {
      id     = "expire-exports"
      status = "Enabled"

      filter {
        prefix = "exports/"
      }

      expiration {
        days = var.current_version_expiration_days
      }
    }
  }
}

# Deny any non-TLS request (§11.5: TLS in transit, explicit in Terraform).
data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid       = "DenyUnEncryptedObjectUploads"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.bucket.json

  depends_on = [aws_s3_bucket_public_access_block.this]
}
