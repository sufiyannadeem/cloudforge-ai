# Namespace-scoped External Secrets Operator JWT identity. Applications do not
# receive GetSecretValue: each continues using its existing Kubernetes Secret.
resource "aws_iam_role" "secret_sync" {
  count = length(var.secret_sync_secret_arns) > 0 ? 1 : 0
  name  = "cloudforge-secret-sync"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = var.runtime_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringEquals = {
        "${local.oidc_issuer}:aud" = "sts.amazonaws.com"
        "${local.oidc_issuer}:sub" = "system:serviceaccount:cloudforge:cloudforge-secret-sync"
      } }
    }]
  })
}

resource "aws_iam_role_policy" "secret_sync" {
  count = length(var.secret_sync_secret_arns) > 0 ? 1 : 0
  role  = aws_iam_role.secret_sync[0].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = var.secret_sync_secret_arns
      }], length(var.secret_sync_kms_key_arns) == 0 ? [] : [{
      Effect   = "Allow"
      Action   = "kms:Decrypt"
      Resource = var.secret_sync_kms_key_arns
      Condition = {
        StringEquals = { "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com" }
        ArnEquals    = { "kms:EncryptionContext:SecretARN" = var.secret_sync_secret_arns }
      }
    }])
  })
}

output "secret_sync_role_arn" {
  value = try(aws_iam_role.secret_sync[0].arn, null)
}
