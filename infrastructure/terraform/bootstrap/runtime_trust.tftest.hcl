mock_provider "aws" {
  override_during = plan
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::cloudforge-test-tfstate" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
}

variables {
  account_id        = "123456789012"
  state_bucket_name = "cloudforge-test-tfstate"
}

run "only_the_configured_service_account_can_federate" {
  command = plan
  variables {
    runtime_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.eu-west-1.amazonaws.com/id/EXAMPLE"
  }
  assert {
    condition     = one(jsondecode(aws_iam_role.infrastructure_service_runtime.assume_role_policy).Statement).Condition.StringEquals["oidc.eks.eu-west-1.amazonaws.com/id/EXAMPLE:sub"] == "system:serviceaccount:cloudforge:cloudforge-infrastructure-service"
    error_message = "The EKS trust policy must check the exact Kubernetes service account."
  }
  assert {
    condition     = one(jsondecode(aws_iam_role.infrastructure_service_runtime.assume_role_policy).Statement).Condition.StringEquals["oidc.eks.eu-west-1.amazonaws.com/id/EXAMPLE:aud"] == "sts.amazonaws.com"
    error_message = "The EKS trust policy must check the STS audience."
  }
}

run "existing_iam_role_trust_remains_supported" {
  command = plan
  variables {
    runtime_principal_arn = "arn:aws:iam::123456789012:role/workload"
  }
  assert {
    condition     = one(jsondecode(aws_iam_role.infrastructure_service_runtime.assume_role_policy).Statement).Principal.AWS == var.runtime_principal_arn
    error_message = "Only the configured workload role may assume the runtime role."
  }
}

run "resource_policies_have_scoped_lifecycle_and_state_access" {
  command = plan
  variables {
    runtime_principal_arn = "arn:aws:iam::123456789012:role/workload"
  }
  assert {
    condition     = length(aws_iam_policy.scoped_provisioning.policy) <= 6144 && length(aws_iam_policy.eks_provisioning.policy) <= 6144
    error_message = "Managed IAM policies must fit within the AWS size limit."
  }
  assert {
    condition     = one([for s in jsondecode(aws_iam_policy.scoped_provisioning.policy).Statement : s if s.Sid == "ManageTaggedInstances"]).Condition.StringEquals["aws:ResourceTag/CloudForge"] == "true"
    error_message = "Termination must be restricted to CloudForge-managed instances."
  }
  assert {
    condition     = toset(one([for s in jsondecode(aws_iam_policy.eks_provisioning.policy).Statement : s if s.Sid == "PassTaggedEKSRolesOnlyToEKS"]).Condition.StringEquals["iam:PassedToService"]) == toset(["eks.amazonaws.com", "ec2.amazonaws.com"])
    error_message = "PassRole must be restricted to the EKS and EC2 services."
  }
  assert {
    condition     = !contains(one([for s in jsondecode(aws_iam_policy.terraform_state_backend.policy).Statement : s if s.Sid == "StateObjects"]).Action, "s3:DeleteObject")
    error_message = "The runtime may delete the lockfile but cannot delete state objects."
  }
}
