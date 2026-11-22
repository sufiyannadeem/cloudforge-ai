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

variable "eks_cluster_version" {
  description = "Kubernetes version for the EKS control plane. Must be in AWS EKS Standard Support. Verified: 1.35 EOL 2027-03-27; 1.32 EOL 2026-03-23 (extended support, $0.60/hr total)."
  type        = string
  default     = "1.35"
}

variable "eks_node_instance_types" {
  description = "EC2 instance types for the AMD64 managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "eks_node_desired_size" {
  description = "Desired number of worker nodes in the default node group."
  type        = number
  default     = 2
}

variable "eks_node_min_size" {
  description = "Minimum number of worker nodes in the default node group."
  type        = number
  default     = 2
}

variable "eks_node_max_size" {
  description = "Maximum number of worker nodes in the default node group."
  type        = number
  default     = 3
}

variable "eks_endpoint_public_access" {
  description = "Enable public API server endpoint access."
  type        = bool
  default     = true
}

variable "eks_public_access_cidrs" {
  description = "CIDR blocks that can access the Amazon EKS public API server endpoint."
  type        = list(string)
  default     = []
}

variable "rds_instance_class" {
  description = "Database instance class for PostgreSQL 16. db.t4g.small required: 4 Go services × 2 replicas × MaxConns=10 = 80 connections needed; db.t4g.micro max_connections≈21 is insufficient."
  type        = string
  default     = "db.t4g.small"
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ deployment for PostgreSQL RDS."
  type        = bool
  default     = false
}

variable "rds_skip_final_snapshot" {
  description = "Skip final DB snapshot on destruction in development."
  type        = bool
  default     = true
}

variable "rds_deletion_protection" {
  description = "Enable deletion protection on PostgreSQL RDS."
  type        = bool
  default     = false
}

# =============================================================================
# API Gateway HTTP API Variables
# =============================================================================

variable "api_gateway_cors_origins" {
  description = "Allowed CORS origins for the API Gateway HTTP API. Set to your domain in production."
  type        = list(string)
  default     = ["*"]

  validation {
    condition     = length(var.api_gateway_cors_origins) > 0
    error_message = "At least one CORS origin must be specified."
  }
}

variable "api_gateway_throttle_burst" {
  description = "API Gateway stage throttle burst limit (requests/second, peak)."
  type        = number
  default     = 100
}

variable "api_gateway_throttle_rate" {
  description = "API Gateway stage throttle steady-state rate limit (requests/second)."
  type        = number
  default     = 50
}

variable "alb_access_log_bucket" {
  description = "Optional existing S3 bucket name for internal ALB access logs. Leave empty to disable."
  type        = string
  default     = ""
}

variable "eks_operator_role_arn" {
  description = "Reviewed existing operator IAM role; no implicit cluster-creator admin."
  type        = string
  default     = ""
  validation {
    condition     = var.eks_operator_role_arn == "" || can(regex("^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", var.eks_operator_role_arn))
    error_message = "Use an existing operator role ARN, never a user or STS session ARN."
  }
}

variable "private_runtime_endpoints" {
  description = "Private STS, EC2 and CloudWatch metrics endpoints for the restricted runtime; one AZ, not HA. NAT remains required for GHCR/controller bootstrap."
  type        = bool
  default     = false
}
