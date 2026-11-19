# =============================================================================
# CloudForge AI — Least-Privilege IAM Trust & Provisioning Roles
# =============================================================================
# Architecture:
# 1. Infrastructure Service Runtime Role: Assumed by the container/pod.
#    Has access to S3 state & native lockfile, and permission to assume
#    the scoped Terraform Provisioner Role.
# 2. Terraform Provisioning Role: Assumed during terraform plan/apply
#    strictly after human approval. Bounded to CloudForge-managed resources.
# =============================================================================

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  partition   = data.aws_partition.current.partition
  oidc_issuer = try(split("oidc-provider/", var.runtime_oidc_provider_arn)[1], "")
}

# -----------------------------------------------------------------------------
# 1. Infrastructure Service Runtime Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "infrastructure_service_runtime" {
  name        = "cloudforge-infrastructure-service-runtime"
  description = "Runtime role for CloudForge Infrastructure Service with S3 state access and assume-role rights."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [for principal in [var.runtime_principal_arn] : {
        Sid       = "TrustConfiguredWorkloadRole"
        Effect    = "Allow"
        Principal = { AWS = principal }
        Action    = "sts:AssumeRole"
      } if principal != ""],
      [for provider in [var.runtime_oidc_provider_arn] : {
        Sid       = "TrustInfrastructureServiceAccount"
        Effect    = "Allow"
        Principal = { Federated = provider }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${local.oidc_issuer}:aud" = "sts.amazonaws.com"
            "${local.oidc_issuer}:sub" = "system:serviceaccount:cloudforge:cloudforge-infrastructure-service"
          }
        }
      } if provider != ""]
    )
  })

  tags = {
    Name              = "cloudforge-infrastructure-service-runtime"
    CloudForgeService = "infrastructure-service"
    CloudForgeManaged = "true"
  }
}

# S3 State & Native Lockfile Policy
# With use_lockfile = true, terraform creates/updates/deletes .tflock objects
# directly in the state bucket.
resource "aws_iam_policy" "terraform_state_backend" {
  name        = "cloudforge-terraform-state-backend"
  description = "Allows access to the S3 state bucket and native lockfile management."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "StateBucketListing"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = aws_s3_bucket.terraform_state.arn
      },
      {
        Sid      = "StateObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.terraform_state.arn}/cloudforge/resources/*/terraform.tfstate"
      },
      {
        Sid      = "NativeStateLocks"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.terraform_state.arn}/cloudforge/resources/*/terraform.tfstate.tflock"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "runtime_attach_state" {
  role       = aws_iam_role.infrastructure_service_runtime.name
  policy_arn = aws_iam_policy.terraform_state_backend.arn
}

# Policy allowing runtime role to assume the Terraform Provisioner Role
resource "aws_iam_policy" "assume_provisioner" {
  name        = "cloudforge-assume-terraform-provisioner"
  description = "Allows infrastructure service runtime to assume the scoped Terraform provisioner role."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowAssumeProvisionerRole"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = aws_iam_role.terraform_provisioner.arn
        Condition = {
          StringEquals = {
            "aws:ResourceTag/CloudForgeManaged" = "true"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "runtime_attach_assume_provisioner" {
  role       = aws_iam_role.infrastructure_service_runtime.name
  policy_arn = aws_iam_policy.assume_provisioner.arn
}

# -----------------------------------------------------------------------------
# 2. Terraform Provisioning Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "terraform_provisioner" {
  name        = "cloudforge-terraform-provisioner"
  description = "Scoped role assumed by Infrastructure Service strictly during plan/apply for resource provisioning."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TrustInfrastructureServiceRuntimeOnly"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.infrastructure_service_runtime.arn
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name              = "cloudforge-terraform-provisioner"
    CloudForgeService = "infrastructure-service"
    CloudForgeManaged = "true"
  }
}

resource "aws_iam_role_policy_attachment" "provisioner_attach_scoped" {
  role       = aws_iam_role.terraform_provisioner.name
  policy_arn = aws_iam_policy.scoped_provisioning.arn
}
