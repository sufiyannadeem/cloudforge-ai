# Single-AZ endpoints keep application AWS API packets inside the VPC and match
# default-deny NetworkPolicy. Controllers and kubelet use NAT for public registries.
# IAM, Cost Explorer and Budgets are NOT covered; Free-plan preview disables them.
resource "aws_security_group" "runtime_endpoints" {
  count       = var.private_runtime_endpoints ? 1 : 0
  name        = "${local.name_prefix}-runtime-endpoints"
  description = "HTTPS to reviewed private runtime AWS endpoints"
  vpc_id      = module.vpc.vpc_id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }
  tags = local.common_tags
}

resource "aws_vpc_endpoint" "runtime" {
  for_each            = var.private_runtime_endpoints ? toset(["sts", "ec2", "monitoring"]) : toset([])
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [module.vpc.private_subnets[0]]
  security_group_ids  = [aws_security_group.runtime_endpoints[0].id]
  tags                = local.common_tags
}
