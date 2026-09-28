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
  description = "AWS account ID used to make the globally unique state bucket name."
  type        = string
  default     = "933018172228"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform state."
  type        = string
  default     = "cloudforge-ai-933018172228-tfstate"
}
