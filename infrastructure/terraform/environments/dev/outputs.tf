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
