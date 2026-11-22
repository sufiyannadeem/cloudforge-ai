output "vpc_id" {
  description = "CloudForge AI VPC ID."
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "CloudForge AI VPC CIDR."
  value       = module.vpc.vpc_cidr_block
}

output "availability_zones" {
  description = "Availability Zones used by CloudForge AI."
  value       = var.availability_zones
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = module.vpc.public_subnets
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = module.vpc.private_subnets
}

output "nat_gateway_ids" {
  description = "NAT Gateway IDs."
  value       = module.vpc.natgw_ids
}

output "ecr_repository_urls" {
  description = "ECR repository URLs."
  value = {
    for name, repository in aws_ecr_repository.services :
    name => repository.repository_url
  }
}

# -----------------------------------------------------------------------------
# EKS Cluster Outputs
# -----------------------------------------------------------------------------
output "eks_cluster_name" {
  description = "Name of the EKS cluster."
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "Endpoint for EKS control plane."
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster."
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "eks_oidc_provider_arn" {
  description = "ARN of the IAM OIDC provider for EKS IRSA."
  value       = aws_iam_openid_connect_provider.eks.arn
}

# -----------------------------------------------------------------------------
# RDS PostgreSQL Outputs
# -----------------------------------------------------------------------------
output "rds_endpoint" {
  description = "Connection endpoint for PostgreSQL RDS."
  value       = aws_db_instance.postgres.endpoint
}

output "rds_address" {
  description = "Hostname of the PostgreSQL RDS instance."
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  description = "Port on which the PostgreSQL RDS instance is listening."
  value       = aws_db_instance.postgres.port
}

output "rds_database_name" {
  description = "Database name on PostgreSQL RDS instance."
  value       = aws_db_instance.postgres.db_name
}

output "rds_master_user_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret managing the master password."
  value       = try(aws_db_instance.postgres.master_user_secret[0].secret_arn, null)
}

# -----------------------------------------------------------------------------
# EFS Storage Outputs
# -----------------------------------------------------------------------------
output "efs_file_system_id" {
  description = "ID of the EFS file system for multi-replica RWX storage."
  value       = aws_efs_file_system.workspaces.id
}

# =============================================================================
# API Gateway + Internal ALB Outputs
# =============================================================================

output "api_gateway_id" {
  description = "ID of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.main.id
}

output "api_gateway_endpoint" {
  description = "Public HTTPS invoke URL for the API Gateway HTTP API ($default stage)."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_gateway_vpc_link_id" {
  description = "ID of the VPC Link connecting API Gateway to the internal ALB."
  value       = aws_apigatewayv2_vpc_link.main.id
}

output "internal_alb_arn" {
  description = "ARN of the internal (non-internet-facing) Application Load Balancer."
  value       = aws_lb.internal.arn
}

output "internal_alb_dns_name" {
  description = "DNS name of the internal ALB (resolves to private IPs; not publicly reachable)."
  value       = aws_lb.internal.dns_name
}

output "frontend_target_group_arn" {
  description = "ARN of the ALB Target Group targeting frontend pods on port 3000."
  value       = aws_lb_target_group.frontend.arn
}

output "internal_alb_listener_arn" {
  description = "Terraform-owned internal listener used by the HTTP API integration."
  value       = aws_lb_listener.internal_http.arn
}

output "internal_alb_subnet_cidrs" {
  description = "ALB source subnets for frontend NetworkPolicy (ALB traffic is not from controller pods)."
  value       = module.vpc.private_subnets_cidr_blocks
}

output "private_runtime_endpoint_ids" {
  description = "Reviewed private STS/EC2/CloudWatch endpoints; no IAM/Cost Explorer coverage implied."
  value       = { for name, endpoint in aws_vpc_endpoint.runtime : name => endpoint.id }
}
