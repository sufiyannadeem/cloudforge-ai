# =============================================================================
# CloudForge AI — Private PostgreSQL 16 RDS Database
# =============================================================================

# -----------------------------------------------------------------------------
# 1. KMS Key for RDS Storage Encryption
# -----------------------------------------------------------------------------
resource "aws_kms_key" "rds" {
  description             = "KMS key for CloudForge AI RDS PostgreSQL storage encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-kms"
  })
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${local.name_prefix}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# -----------------------------------------------------------------------------
# 2. Database Subnet Group (Private Subnets Only)
# -----------------------------------------------------------------------------
resource "aws_db_subnet_group" "rds" {
  name        = "${local.name_prefix}-db-subnets"
  description = "Private subnet group for CloudForge AI PostgreSQL database"
  subnet_ids  = module.vpc.private_subnets

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db-subnet-group"
  })
}

# -----------------------------------------------------------------------------
# 3. Security Group for RDS (Internal Ingress on 5432 Only)
# -----------------------------------------------------------------------------
resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Security group for CloudForge AI PostgreSQL RDS instance"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL access from VPC private subnets"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }

  # Mount targets/database do not initiate client connections. Security-group
  # statefulness permits replies to the narrowly allowed inbound connections.
  # Explicit empty list also revokes previously managed allow-all egress.
  egress = []

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-sg"
  })
}

# -----------------------------------------------------------------------------
# 4. PostgreSQL 16 Parameter Group (Enforce TLS)
# -----------------------------------------------------------------------------
resource "aws_db_parameter_group" "postgres16" {
  name        = "${local.name_prefix}-pg16-params"
  family      = "postgres16"
  description = "CloudForge AI PostgreSQL 16 parameter group with TLS enforcement"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 5. PostgreSQL 16 RDS Instance
# -----------------------------------------------------------------------------
resource "aws_db_instance" "postgres" {
  identifier     = "${local.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = "16.15" # Read-only regional orderability verified 2026-11-22.

  instance_class        = var.rds_instance_class
  allocated_storage     = 20
  max_allocated_storage = 0 # Disable automatic storage growth for the capped demo.
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.rds.arn

  db_name  = "cloudforge"
  username = "postgres"

  # Managed master password in AWS Secrets Manager
  manage_master_user_password   = true
  master_user_secret_kms_key_id = aws_kms_key.rds.arn

  db_subnet_group_name   = aws_db_subnet_group.rds.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  publicly_accessible = false
  multi_az            = var.rds_multi_az

  skip_final_snapshot = var.rds_skip_final_snapshot
  deletion_protection = var.rds_deletion_protection

  auto_minor_version_upgrade = true
  # RDS T4g uses Unlimited mode; preflight includes worst-case surplus CPU credits.
  copy_tags_to_snapshot   = true
  backup_retention_period = 7

  tags = merge(local.common_tags, {
    Name                      = "${local.name_prefix}-postgres"
    "cloudforge.ai/component" = "database"
  })
}
