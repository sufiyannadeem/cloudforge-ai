module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "6.7.3"

  name = "${local.name_prefix}-vpc"
  cidr = var.vpc_cidr

  azs = var.availability_zones

  private_subnets = [
    "10.40.10.0/24",
    "10.40.20.0/24",
    "10.40.30.0/24"
  ]

  public_subnets = [
    "10.40.110.0/24",
    "10.40.120.0/24",
    "10.40.130.0/24"
  ]

  enable_nat_gateway = var.enable_nat_gateway
  single_nat_gateway = var.single_nat_gateway

  enable_dns_hostnames = true
  enable_dns_support   = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }

  tags = local.common_tags
}
