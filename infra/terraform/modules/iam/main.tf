# ---------------------------------------------------------------------------
# Workload identity via EKS Pod Identity (§10, primary model). For each
# workload (api, worker) we create an IAM role trusted by the Pod Identity
# service principal and bind it to a (namespace, service-account) pair with an
# aws_eks_pod_identity_association. Permissions are least-privilege and scoped
# to this env's export bucket + secret ARNs.
#
# IRSA fallback (documented, not wired here):
#   If Pod Identity is unavailable, the same roles can instead trust the
#   cluster OIDC provider. The federated trust looks like:
#
#     principals { type = "Federated"; identifiers = [<oidc_provider_arn>] }
#     condition StringEquals on
#       "<oidc>:sub" = "system:serviceaccount:<ns>:<sa>"
#       "<oidc>:aud" = "sts.amazonaws.com"
#
#   and the service account is annotated with
#   eks.amazonaws.com/role-arn=<role_arn>. The permission policies below are
#   identical in both models — only the trust policy differs.
# ---------------------------------------------------------------------------

locals {
  workloads = {
    api = {
      service_account = var.api_service_account
      # API issues pre-signed URLs (read) and triggers exports.
      s3_actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    }
    worker = {
      service_account = var.worker_service_account
      # Workers render and upload exports, then clean up.
      s3_actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    }
  }
}

data "aws_iam_policy_document" "pod_identity_assume" {
  statement {
    effect = "Allow"
    actions = [
      "sts:AssumeRole",
      "sts:TagSession",
    ]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "workload" {
  for_each = local.workloads

  name               = "${var.name_prefix}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json

  tags = merge(var.tags, {
    Name     = "${var.name_prefix}-${each.key}"
    Workload = each.key
  })
}

# ----------------------------- Permission policy ---------------------------

data "aws_iam_policy_document" "workload" {
  for_each = local.workloads

  # Object-level access scoped to this bucket only.
  statement {
    sid    = "ReportExportObjects"
    effect = "Allow"
    actions = [
      for a in each.value.s3_actions : a if a != "s3:ListBucket"
    ]
    resources = ["${var.export_bucket_arn}/*"]
  }

  # ListBucket is a bucket-level action; scope it to the export prefix.
  statement {
    sid       = "ReportExportList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.export_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["exports/*"]
    }
  }

  # KMS for the export bucket CMK (SSE-KMS get/put).
  statement {
    sid    = "ReportExportKms"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.export_bucket_kms_key_arn]
  }

  # Read only the specific secrets this env owns.
  statement {
    sid    = "ReadSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = var.secret_arns
  }

  # KMS decrypt for the secret CMKs (only added when key ARNs are supplied).
  dynamic "statement" {
    for_each = length(var.secret_kms_key_arns) > 0 ? [1] : []

    content {
      sid       = "DecryptSecretsKms"
      effect    = "Allow"
      actions   = ["kms:Decrypt"]
      resources = var.secret_kms_key_arns
    }
  }
}

resource "aws_iam_role_policy" "workload" {
  for_each = local.workloads

  name   = "${var.name_prefix}-${each.key}-access"
  role   = aws_iam_role.workload[each.key].id
  policy = data.aws_iam_policy_document.workload[each.key].json
}

# --------------------------- Pod Identity binding --------------------------

resource "aws_eks_pod_identity_association" "workload" {
  for_each = local.workloads

  cluster_name    = var.cluster_name
  namespace       = var.namespace
  service_account = each.value.service_account
  role_arn        = aws_iam_role.workload[each.key].arn

  tags = merge(var.tags, {
    Workload = each.key
  })
}
