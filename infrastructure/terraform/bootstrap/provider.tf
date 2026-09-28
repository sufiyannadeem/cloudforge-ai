provider "aws" {
  region = var.aws_region

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
