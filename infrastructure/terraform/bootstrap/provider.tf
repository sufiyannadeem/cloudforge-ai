provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = "bootstrap"
      ManagedBy   = "terraform"
      Repository  = "cloudforge-ai"
      Purpose     = "terraform-state"
    }
  }
}
