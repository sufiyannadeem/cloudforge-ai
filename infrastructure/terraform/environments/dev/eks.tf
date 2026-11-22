# =============================================================================
# CloudForge AI — EKS Cluster and AMD64 Managed Node Group
# =============================================================================

# -----------------------------------------------------------------------------
# 1. KMS Key for EKS Secrets Encryption
# -----------------------------------------------------------------------------
resource "aws_kms_key" "eks" {
  description             = "KMS key for CloudForge AI EKS cluster secrets encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-eks-kms"
  })
}

resource "aws_kms_alias" "eks" {
  name          = "alias/${local.name_prefix}-eks"
  target_key_id = aws_kms_key.eks.key_id
}

# -----------------------------------------------------------------------------
# 2. EKS Cluster Control Plane IAM Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "eks_cluster" {
  name        = "${local.name_prefix}-eks-cluster-role"
  description = "IAM role for CloudForge AI EKS control plane"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster.name
}

# -----------------------------------------------------------------------------
# 3. EKS Cluster Security Group
# -----------------------------------------------------------------------------
resource "aws_security_group" "eks_cluster" {
  name        = "${local.name_prefix}-eks-cluster-sg"
  description = "Security group for CloudForge AI EKS control plane communication"
  vpc_id      = module.vpc.vpc_id

  # Control-plane API/kubelet, LBC admission and metrics-server aggregated API.
  # No registry/image-pull or arbitrary internet egress belongs on this extra SG.
  dynamic "egress" {
    for_each = toset([443, 10250, 9443, 10251])
    content {
      description = "Control plane to private node and admission endpoints"
      protocol    = "tcp"
      from_port   = egress.value
      to_port     = egress.value
      cidr_blocks = module.vpc.private_subnets_cidr_blocks
    }
  }
  dynamic "egress" {
    for_each = toset(["tcp", "udp"])
    content {
      description = "DNS within private node subnets"
      protocol    = egress.value
      from_port   = 53
      to_port     = 53
      cidr_blocks = module.vpc.private_subnets_cidr_blocks
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-eks-cluster-sg"
  })
}

# -----------------------------------------------------------------------------
# 4. EKS Cluster
# -----------------------------------------------------------------------------
resource "aws_eks_cluster" "main" {
  name     = "${local.name_prefix}-eks"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.eks_cluster_version

  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }

  lifecycle {
    precondition {
      condition     = var.eks_operator_role_arn != ""
      error_message = "Provide the existing reviewed operator role before creating EKS."
    }
    precondition {
      condition     = var.eks_operator_security_group_id != ""
      error_message = "Provide the reviewed SG of an existing VPC-connected operator before creating private EKS."
    }
  }

  vpc_config {
    subnet_ids              = module.vpc.private_subnets
    endpoint_private_access = true
    endpoint_public_access  = false
    # Inert while public access is disabled; never inherit the AWS 0.0.0.0/0 default.
    # This is NOT the access control for the private endpoint (SGs enforce that).
    public_access_cidrs = [var.vpc_cidr]
    security_group_ids  = [aws_security_group.eks_cluster.id]
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.eks.arn
    }
    resources = ["secrets"]
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  tags = merge(local.common_tags, {
    Name                      = "${local.name_prefix}-eks"
    "cloudforge.ai/component" = "control-plane"
  })

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_resource_controller,
    aws_cloudwatch_log_group.eks
  ]
}

# Existing VPC-connected operator identity, not a new bastion/VPN or public CIDR.
resource "aws_vpc_security_group_ingress_rule" "operator_api" {
  security_group_id            = aws_security_group.eks_cluster.id
  referenced_security_group_id = var.eks_operator_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Private EKS API from reviewed operator SG only"
}

# -----------------------------------------------------------------------------
# 5. IAM OIDC Provider for Pod Identity / IRSA
# -----------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list = ["sts.amazonaws.com"]
  url            = aws_eks_cluster.main.identity[0].oidc[0].issuer

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-eks-oidc"
  })
}

# -----------------------------------------------------------------------------
# 6. EKS Managed Node Group IAM Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "eks_nodes" {
  name        = "${local.name_prefix}-eks-node-role"
  description = "IAM role for CloudForge AI EKS worker nodes"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_ecr_read_only" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

# -----------------------------------------------------------------------------
# 7. AMD64 EKS Managed Node Group
# -----------------------------------------------------------------------------
resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${local.name_prefix}-default-pool"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = module.vpc.private_subnets

  ami_type       = "AL2023_x86_64_STANDARD"
  instance_types = var.eks_node_instance_types
  capacity_type  = "ON_DEMAND"

  launch_template {
    id      = aws_launch_template.nodes.id
    version = aws_launch_template.nodes.latest_version
  }

  scaling_config {
    desired_size = var.eks_node_desired_size
    min_size     = var.eks_node_min_size
    max_size     = var.eks_node_max_size
  }

  lifecycle {
    ignore_changes = [scaling_config[0].desired_size]
  }

  update_config {
    update_strategy = "MINIMAL" # No six-node multi-AZ surge; planned drain still required.
    max_unavailable = 1
  }

  labels = {
    "cloudforge.ai/component" = "node-autoscaler"
  }

  tags = merge(local.common_tags, {
    Name                                                 = "${local.name_prefix}-node"
    "k8s.io/cluster-autoscaler/enabled"                  = "true"
    "k8s.io/cluster-autoscaler/${local.name_prefix}-eks" = "owned"
  })

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_ecr_read_only
  ]
}

# Managed-node-group tags are not propagated to the underlying ASG.
resource "aws_autoscaling_group_tag" "discovery" {
  for_each = {
    "k8s.io/cluster-autoscaler/enabled"                  = "true"
    "k8s.io/cluster-autoscaler/${local.name_prefix}-eks" = "owned"
  }
  autoscaling_group_name = aws_eks_node_group.default.resources[0].autoscaling_groups[0].name
  tag {
    key                 = each.key
    value               = each.value
    propagate_at_launch = false
  }
}

resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/${local.name_prefix}-eks/cluster"
  retention_in_days = 7
  tags              = local.common_tags
}

resource "aws_eks_access_entry" "operator" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = var.eks_operator_role_arn
  type          = "STANDARD"
  tags          = local.common_tags
}

resource "aws_eks_access_policy_association" "operator" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_eks_access_entry.operator.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
}

resource "aws_launch_template" "nodes" {
  name_prefix = "${local.name_prefix}-nodes-"
  lifecycle {
    precondition {
      condition = length(var.eks_node_instance_types) > 0 && (
        alltrue([for instance_type in var.eks_node_instance_types : can(regex("^t[0-9][a-z]*\\.", instance_type))]) ||
        alltrue([for instance_type in var.eks_node_instance_types : !can(regex("^t[0-9][a-z]*\\.", instance_type))])
      )
      error_message = "Use a nonempty uniform credit-mode pool; do not mix burstable and nonburstable instance types."
    }
  }
  # Budget protection: no unbounded T3 surplus-credit charge. Sustained CPU can throttle.
  dynamic "credit_specification" {
    # Nonburstable M/C nodes do not support credit_specification. Mixed T/M
    # lists must not silently turn T nodes into billable Unlimited mode.
    for_each = anytrue([for instance_type in var.eks_node_instance_types : can(regex("^t[0-9][a-z]*\\.", instance_type))]) ? [1] : []
    content { cpu_credits = "standard" }
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  tags = local.common_tags
}
