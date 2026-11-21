locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  ecr_repositories = {
    frontend               = "cloudforge/frontend"
    project_service        = "cloudforge/project-service"
    infrastructure_service = "cloudforge/infrastructure-service"
    deployment_service     = "cloudforge/deployment-service"
    aiops_service          = "cloudforge/aiops-service"
  }
}
