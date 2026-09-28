terraform {
  backend "s3" {
    bucket       = "cloudforge-ai-933018172228-tfstate"
    key          = "environments/dev/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
