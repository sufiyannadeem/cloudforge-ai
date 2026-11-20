variable "aws_region" {
  description = "AWS region for the Terraform state bucket."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name."
  type        = string
  default     = "cloudforge-ai"
}

variable "account_id" {
  description = "Expected AWS account ID for the bootstrap."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform state."
  type        = string

}

variable "runtime_principal_arn" {
  description = "Optional existing IAM role allowed to assume the infrastructure runtime role."
  type        = string
  default     = ""

  validation {
    condition     = var.runtime_principal_arn == "" || can(regex("^arn:aws(-[a-z-]+)?:iam::${var.account_id}:role/[A-Za-z0-9+=,.@_/-]+$", var.runtime_principal_arn))
    error_message = "Provide an existing IAM role ARN in the bootstrap account."
  }
}

variable "runtime_oidc_provider_arn" {
  description = "Existing EKS IAM OIDC provider ARN for the cloudforge-infrastructure-service service account."
  type        = string
  default     = ""

  validation {
    condition     = (var.runtime_oidc_provider_arn != "") != (var.runtime_principal_arn != "")
    error_message = "Configure exactly one runtime trust source: IAM role or EKS OIDC provider."
  }

  validation {
    condition     = var.runtime_oidc_provider_arn == "" || can(regex("^arn:aws(-[a-z-]+)?:iam::${var.account_id}:oidc-provider/oidc\\.eks\\.[a-z0-9-]+\\.amazonaws\\.com(\\.cn)?/id/[A-Za-z0-9]+$", var.runtime_oidc_provider_arn))
    error_message = "Provide the EKS IAM OIDC provider ARN in the bootstrap account."
  }
}

variable "application_bucket_names" {
  description = "Explicit reviewed application buckets; empty disables S3 provisioning. Never include the state bucket."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for name in var.application_bucket_names : can(regex("^cloudforge-[a-z0-9][a-z0-9.-]+[a-z0-9]$", name)) && length(name) <= 63 && name != var.state_bucket_name])
    error_message = "Application buckets must be exact cloudforge-* names distinct from the state bucket."
  }
}

variable "secret_sync_secret_arns" {
  description = "Exact existing Secrets Manager ARNs for the namespace-scoped sync identity; empty disables the role."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for arn in var.secret_sync_secret_arns : can(regex("^arn:aws:secretsmanager:${var.aws_region}:${var.account_id}:secret:[A-Za-z0-9/_+=.@-]+$", arn))]) && (length(var.secret_sync_secret_arns) == 0 || var.runtime_oidc_provider_arn != "")
    error_message = "Secret sync requires EKS OIDC and exact same-account/region secret ARNs without wildcards."
  }
}

variable "secret_sync_kms_key_arns" {
  description = "Exact customer KMS keys encrypting the approved secrets; omit for AWS-managed keys."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for arn in var.secret_sync_kms_key_arns : can(regex("^arn:aws:kms:${var.aws_region}:${var.account_id}:key/[a-f0-9-]+$", arn))]) && (length(var.secret_sync_kms_key_arns) == 0 || length(var.secret_sync_secret_arns) > 0)
    error_message = "Use exact same-account/region KMS key ARNs only with configured secrets."
  }
}

variable "state_access_log_bucket_name" {
  description = "Approved existing S3 access-log destination in this account and region, with log-delivery permissions. Must differ from the state bucket."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_access_log_bucket_name)) && var.state_access_log_bucket_name != var.state_bucket_name
    error_message = "Provide an approved access-log bucket distinct from the Terraform state bucket."
  }
}
