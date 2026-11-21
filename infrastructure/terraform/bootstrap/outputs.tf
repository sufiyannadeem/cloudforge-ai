output "terraform_state_bucket_name" {
  description = "Terraform state S3 bucket."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "terraform_state_bucket_arn" {
  description = "Terraform state S3 bucket ARN."
  value       = aws_s3_bucket.terraform_state.arn
}

output "infrastructure_service_runtime_role_arn" {
  description = "ARN of the Infrastructure Service runtime IAM role."
  value       = aws_iam_role.infrastructure_service_runtime.arn
}

output "terraform_provisioner_role_arn" {
  description = "ARN of the scoped Terraform provisioner IAM role."
  value       = aws_iam_role.terraform_provisioner.arn
}
