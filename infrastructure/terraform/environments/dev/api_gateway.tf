# =============================================================================
# CloudForge AI — API Gateway HTTP API + VPC Link + Internal ALB
# =============================================================================
# Architecture:
#   Internet → API Gateway HTTP API (HTTPS, public endpoint, managed TLS)
#              → VPC Link (private, stays in AWS backbone)
#              → Internal ALB (scheme=internal, private subnets only)
#              → frontend ClusterIP :3000 via Target Group
#
# The ALB has internal=true; tags do not enforce its scheme.
# The API Gateway endpoint is the sole public entry point; no ALB listener
# is exposed directly to the internet.
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Security Group: Internal ALB
#    Allows private HTTP only from VPC Link ENIs; pod egress is port3000 only.
# -----------------------------------------------------------------------------
resource "aws_security_group" "internal_alb" {
  name        = "${local.name_prefix}-internal-alb-sg"
  description = "Internal ALB for CloudForge AI — allows traffic only from API Gateway VPC Link ENIs within the VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "HTTP from VPC Link ENIs (API Gateway keeps TLS; ALB receives HTTP inside VPC)"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.vpc_link.id]
  }

  egress {
    description = "Forward to EKS nodes on frontend pod port"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }

  tags = merge(local.common_tags, {
    Name                      = "${local.name_prefix}-internal-alb-sg"
    "cloudforge.ai/component" = "internal-alb"
    # Explicit guard: this SG must only be attached to internal scheme ALBs.
    "cloudforge.ai/alb-scheme" = "internal"
  })
}

# Separate ENI identity: VPC Link sends HTTP to the ALB listener, not pod port 3000.
resource "aws_security_group" "vpc_link" {
  name        = "${local.name_prefix}-vpc-link-sg"
  description = "API Gateway VPC Link ENIs"
  vpc_id      = module.vpc.vpc_id
  tags        = local.common_tags
}

resource "aws_vpc_security_group_egress_rule" "vpc_link_alb" {
  security_group_id            = aws_security_group.vpc_link.id
  referenced_security_group_id = aws_security_group.internal_alb.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
}

# VPC CNI pods use node SGs unless Security Groups for Pods is enabled.
resource "aws_vpc_security_group_ingress_rule" "alb_frontend" {
  security_group_id            = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.internal_alb.id
  from_port                    = 3000
  to_port                      = 3000
  ip_protocol                  = "tcp"
}

# -----------------------------------------------------------------------------
# 2. Internal Application Load Balancer
#    scheme = "internal" → never internet-facing; serves VPC-internal traffic only.
# -----------------------------------------------------------------------------
resource "aws_lb" "internal" {
  name                       = "${local.name_prefix}-internal-alb"
  internal                   = true # Non-internet-facing — mandatory requirement.
  load_balancer_type         = "application"
  drop_invalid_header_fields = true
  security_groups            = [aws_security_group.internal_alb.id]
  subnets                    = module.vpc.private_subnets

  # Access logging bucket is optional; set var.alb_access_log_bucket to enable.
  dynamic "access_logs" {
    for_each = var.alb_access_log_bucket != "" ? [1] : []
    content {
      bucket  = var.alb_access_log_bucket
      enabled = true
    }
  }

  tags = merge(local.common_tags, {
    Name                       = "${local.name_prefix}-internal-alb"
    "cloudforge.ai/component"  = "internal-alb"
    "cloudforge.ai/alb-scheme" = "internal"
  })
}

# -----------------------------------------------------------------------------
# 3. Target Group: forward to frontend pods on port 3000
#    target_type = "ip" to target pod IPs directly (required for EKS with VPC CNI).
# -----------------------------------------------------------------------------
resource "aws_lb_target_group" "frontend" {
  name        = "${local.name_prefix}-frontend-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/login" # Existing unauthenticated frontend route; /health does not exist.
    protocol            = "HTTP"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = merge(local.common_tags, {
    Name                      = "${local.name_prefix}-frontend-tg"
    "cloudforge.ai/component" = "frontend"
  })
}

# -----------------------------------------------------------------------------
# 4. ALB HTTP Listener (port 80, internal only — API Gateway terminates TLS)
# -----------------------------------------------------------------------------
# API Gateway's public endpoint terminates HTTPS. This single listener is private:
# internal ALB + private subnets + ingress only from the VPC Link security group.
# No ACM/private-TLS service is introduced. See PRIVATE_NETWORK_SECURITY.md for
# the plaintext risk, exact scope, guard tests and mandatory review conditions.
#trivy:ignore:AVD-AWS-0054:exp:2026-12-22
resource "aws_lb_listener" "internal_http" {
  load_balancer_arn = aws_lb.internal.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 5. VPC Link (HTTP API style — uses the internal ALB via subnet/SG ENIs)
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_vpc_link" "main" {
  name               = "${local.name_prefix}-vpc-link"
  security_group_ids = [aws_security_group.vpc_link.id]
  subnet_ids         = module.vpc.private_subnets

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-vpc-link"
  })
}

# -----------------------------------------------------------------------------
# 6. API Gateway HTTP API
#    Single public HTTPS endpoint. TLS is managed by API Gateway (no ACM cert
#    procurement required for the default execute-api domain). A custom domain
#    with an ACM certificate can be added via aws_apigatewayv2_domain_name.
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_api" "main" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "CloudForge AI public HTTP API — sole internet-facing entry point"

  cors_configuration {
    allow_origins = var.api_gateway_cors_origins
    allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers = ["content-type", "authorization", "x-cloudforge-request-id"]
    max_age       = 300
  }

  tags = merge(local.common_tags, {
    Name                      = "${local.name_prefix}-api"
    "cloudforge.ai/component" = "api-gateway"
  })
}

# -----------------------------------------------------------------------------
# 7. CloudWatch Log Group for API Gateway access logs
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = 7

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 9. API Gateway Integration: HTTP_PROXY → VPC Link → Internal ALB
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_integration" "frontend_proxy" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "HTTP_PROXY"

  integration_method = "ANY"
  integration_uri    = aws_lb_listener.internal_http.arn

  connection_type = "VPC_LINK"
  connection_id   = aws_apigatewayv2_vpc_link.main.id

  # Strip the stage prefix; forwarded headers are reserved by HTTP API mapping.
  request_parameters = {
    "overwrite:path" = "$request.path"
  }

  payload_format_version = "1.0"
}

# -----------------------------------------------------------------------------
# 10. API Gateway Route: catch-all proxy to frontend
#     All paths /{proxy+} and / are forwarded through the VPC Link.
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_route" "proxy_all" {
  api_id             = aws_apigatewayv2_api.main.id
  authorization_type = "NONE" # Frontend session/RBAC/CSRF protects application routes.
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.frontend_proxy.id}"
}

resource "aws_apigatewayv2_route" "root" {
  api_id             = aws_apigatewayv2_api.main.id
  authorization_type = "NONE" # Login, health and static assets must be reachable.
  route_key          = "ANY /"
  target             = "integrations/${aws_apigatewayv2_integration.frontend_proxy.id}"
}

# -----------------------------------------------------------------------------
# 11. API Gateway Stage ($default — auto-deployed)
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      sourceIp         = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      responseLength   = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    throttling_burst_limit = var.api_gateway_throttle_burst
    throttling_rate_limit  = var.api_gateway_throttle_rate
  }

  tags = local.common_tags

}
