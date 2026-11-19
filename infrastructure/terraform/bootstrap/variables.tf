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
