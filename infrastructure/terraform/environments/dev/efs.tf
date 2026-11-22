# =============================================================================
# CloudForge AI — AWS EFS FileSystem for Multi-Replica RWX Storage
# =============================================================================
# Used by infrastructure-service for cloudforge-terraform-workspaces PVC (ReadWriteMany)
# to ensure saved Terraform plan artifacts survive pod restarts and cross-replica routing.

# -----------------------------------------------------------------------------
# 1. KMS Key for EFS Encryption
# -----------------------------------------------------------------------------
resource "aws_kms_key" "efs" {
  description             = "KMS key for CloudForge AI EFS storage encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-efs-kms"
  })
}

resource "aws_kms_alias" "efs" {
  name          = "alias/${local.name_prefix}-efs"
  target_key_id = aws_kms_key.efs.key_id
}

# -----------------------------------------------------------------------------
# 2. Security Group for EFS Mount Targets (NFS 2049 within private subnets)
# -----------------------------------------------------------------------------
resource "aws_security_group" "efs" {
  name        = "${local.name_prefix}-efs-sg"
  description = "Security group for CloudForge AI EFS mount targets"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "NFS access from VPC private subnets"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-efs-sg"
  })
}

# -----------------------------------------------------------------------------
# 3. EFS FileSystem
# -----------------------------------------------------------------------------
resource "aws_efs_file_system" "workspaces" {
  creation_token   = "${local.name_prefix}-terraform-workspaces"
  encrypted        = true
  kms_key_id       = aws_kms_key.efs.arn
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  tags = merge(local.common_tags, {
    Name                      = "${local.name_prefix}-terraform-workspaces"
    "cloudforge.ai/component" = "shared-storage"
  })
}

# -----------------------------------------------------------------------------
# 4. EFS Mount Targets (one per private subnet AZ)
# -----------------------------------------------------------------------------
resource "aws_efs_mount_target" "private" {
  count           = length(module.vpc.private_subnets)
  file_system_id  = aws_efs_file_system.workspaces.id
  subnet_id       = module.vpc.private_subnets[count.index]
  security_groups = [aws_security_group.efs.id]
}
