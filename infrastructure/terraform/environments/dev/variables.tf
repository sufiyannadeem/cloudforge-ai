variable "aws_region" {
  description = "AWS region where CloudForge AI infrastructure is deployed."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name used for resource naming and tags."
  type        = string
  default     = "cloudforge-ai"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the CloudForge AI VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "availability_zones" {
  description = "Availability Zones used by the environment."
  type        = list(string)

  default = [
    "eu-west-1a",
    "eu-west-1b",
    "eu-west-1c"
  ]

  validation {
    condition     = length(var.availability_zones) >= 3
    error_message = "CloudForge AI requires at least three Availability Zones."
  }
}

variable "single_nat_gateway" {
  description = "Use one NAT Gateway to reduce development environment cost."
  type        = bool
  default     = true
}

variable "ecr_image_tag_mutability" {
  description = "Whether ECR image tags can be overwritten."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.ecr_image_tag_mutability)
    error_message = "ECR image tag mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "enable_nat_gateway" {
  description = "Whether the development VPC should create a NAT Gateway."
  type        = bool
  default     = false
}
