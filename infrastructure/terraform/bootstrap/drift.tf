variable "enable_drift_reader" {
  type    = bool
  default = false
}

# No write, PassRole, state-lock or assume-provisioner permissions. RDS secret
# reads are intentionally not granted by default: review those separately if needed.
resource "aws_iam_role" "drift_reader" {
  count = var.enable_drift_reader ? 1 : 0
  name  = "cloudforge-drift-reader"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = var.runtime_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringEquals = {
        "${local.oidc_issuer}:aud" = "sts.amazonaws.com"
        "${local.oidc_issuer}:sub" = "system:serviceaccount:cloudforge:cloudforge-drift"
      } }
    }]
  })
  lifecycle {
    precondition {
      condition     = var.runtime_oidc_provider_arn != ""
      error_message = "Drift reader requires the verified EKS OIDC provider."
    }
  }
}

resource "aws_iam_role_policy" "drift_reader" {
  count = var.enable_drift_reader ? 1 : 0
  role  = aws_iam_role.drift_reader[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketLocation"]
        Resource = aws_s3_bucket.terraform_state.arn
      },
      {
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.terraform_state.arn}/cloudforge/resources/*/terraform.tfstate"
      },
      {
        Effect    = "Allow"
        Action    = ["ec2:DescribeInstances", "ec2:DescribeInstanceAttribute", "ec2:DescribeImages", "ec2:DescribeVolumes", "ec2:DescribeNetworkInterfaces", "ec2:DescribeVpcs", "ec2:DescribeVpcAttribute", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeTags", "rds:DescribeDBInstances", "rds:DescribeDBSubnetGroups", "rds:ListTagsForResource", "eks:DescribeCluster", "eks:DescribeNodegroup", "eks:ListTagsForResource"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:RequestedRegion" = var.aws_region } }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:GetRole", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies"]
        Resource = "arn:${local.partition}:iam::${var.account_id}:role/cloudforge-*"
      }
      ], length(var.application_bucket_names) > 0 ? [{
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation", "s3:GetBucketAcl", "s3:GetBucketLogging", "s3:GetBucketCORS", "s3:GetBucketObjectLockConfiguration", "s3:GetBucketRequestPayment", "s3:GetLifecycleConfiguration", "s3:GetBucketPolicy", "s3:GetBucketPublicAccessBlock", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration", "s3:GetBucketTagging"]
        Resource = [for name in var.application_bucket_names : "arn:${local.partition}:s3:::${name}"]
    }] : [])
  })
}

output "drift_reader_role_arn" {
  value = var.enable_drift_reader ? aws_iam_role.drift_reader[0].arn : null
}
