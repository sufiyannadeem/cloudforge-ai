locals {
  ec2_arn    = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}"
  eks_arn    = "arn:${local.partition}:eks:${var.aws_region}:${local.account_id}"
  rds_arn    = "arn:${local.partition}:rds:${var.aws_region}:${local.account_id}"
  iam_role   = "arn:${local.partition}:iam::${local.account_id}:role"
  aws_policy = "arn:${local.partition}:iam::aws:policy"

  request_managed  = { StringEquals = { "aws:RequestTag/CloudForge" = "true" } }
  resource_managed = { StringEquals = { "aws:ResourceTag/CloudForge" = "true" } }

  eks_roles = {
    cluster = {
      arn      = "${local.iam_role}/cloudforge-eks-cluster-role-*"
      policies = ["AmazonEKSClusterPolicy"]
    }
    node = {
      arn      = "${local.iam_role}/cloudforge-eks-node-role-*"
      policies = ["AmazonEKSWorkerNodePolicy", "AmazonEKS_CNI_Policy", "AmazonEC2ContainerRegistryReadOnly"]
    }
  }
}

resource "aws_iam_policy" "scoped_provisioning" {
  name        = "cloudforge-scoped-provisioning"
  description = "Regional, resource-scoped provisioning permissions for CloudForge."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RegionalInventory"
        Effect = "Allow"
        Action = [
          "ec2:DescribeAccountAttributes", "ec2:DescribeAvailabilityZones",
          "ec2:DescribeImages", "ec2:DescribeInstances", "ec2:DescribeInstanceAttribute", "ec2:DescribeInstanceCreditSpecifications",
          "ec2:DescribeInstanceTypes", "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeSecurityGroups", "ec2:DescribeSubnets", "ec2:DescribeTags",
          "ec2:DescribeVolumes", "ec2:DescribeVpcAttribute", "ec2:DescribeVpcs",
          "eks:DescribeClusterVersions", "rds:DescribeDBInstances",
          "rds:DescribeDBSubnetGroups", "rds:DescribeDBEngineVersions",
          "rds:DescribeOrderableDBInstanceOptions"
        ]
        Resource  = "*"
        Condition = { StringEquals = { "aws:RequestedRegion" = var.aws_region } }
      },
      {
        Sid    = "LaunchDependencies"
        Effect = "Allow"
        Action = "ec2:RunInstances"
        Resource = concat(
          ["arn:${local.partition}:ec2:${var.aws_region}::image/ami-*"],
          [for kind in ["key-pair", "network-interface", "security-group", "subnet", "volume"] : "${local.ec2_arn}:${kind}/*"]
        )
      },
      {
        Sid       = "CreateTaggedInstances"
        Effect    = "Allow"
        Action    = "ec2:RunInstances"
        Resource  = "${local.ec2_arn}:instance/*"
        Condition = local.request_managed
      },
      {
        Sid       = "CreateTaggedVPC"
        Effect    = "Allow"
        Action    = "ec2:CreateVpc"
        Resource  = "${local.ec2_arn}:vpc/*"
        Condition = local.request_managed
      },
      {
        Sid      = "TagDuringEC2Creation"
        Effect   = "Allow"
        Action   = "ec2:CreateTags"
        Resource = [for kind in ["instance", "volume", "network-interface", "vpc"] : "${local.ec2_arn}:${kind}/*"]
        Condition = {
          StringEquals = { "ec2:CreateAction" = ["RunInstances", "CreateVpc"] }
        }
      },
      {
        Sid       = "ManageTaggedInstances"
        Effect    = "Allow"
        Action    = ["ec2:ModifyInstanceAttribute", "ec2:StartInstances", "ec2:StopInstances", "ec2:TerminateInstances"]
        Resource  = "${local.ec2_arn}:instance/*"
        Condition = local.resource_managed
      },
      {
        Sid       = "ManageTaggedVPC"
        Effect    = "Allow"
        Action    = ["ec2:DeleteVpc", "ec2:ModifyVpcAttribute"]
        Resource  = "${local.ec2_arn}:vpc/*"
        Condition = local.resource_managed
      },
      {
        Sid      = "UpdateManagedEC2Tags"
        Effect   = "Allow"
        Action   = ["ec2:CreateTags", "ec2:DeleteTags"]
        Resource = ["${local.ec2_arn}:instance/*", "${local.ec2_arn}:vpc/*"]
        Condition = {
          StringEquals                             = local.resource_managed.StringEquals
          "ForAllValues:StringNotEqualsIgnoreCase" = { "aws:TagKeys" = "CloudForge" }
        }
      },
      {
        Sid      = "ResolvePublicAMIs"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:${local.partition}:ssm:${var.aws_region}::parameter/aws/service/*"
      },
      {
        Sid      = "ProtectTerraformState"
        Effect   = "Deny"
        Action   = "s3:*"
        Resource = [aws_s3_bucket.terraform_state.arn, "${aws_s3_bucket.terraform_state.arn}/*"]
      },
      {
        Sid    = "ManageApplicationBuckets"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket", "s3:DeleteBucket", "s3:GetBucketLocation", "s3:ListBucket",
          "s3:GetBucketAcl", "s3:GetBucketLogging", "s3:GetBucketCORS", "s3:GetBucketObjectLockConfiguration",
          "s3:GetBucketRequestPayment", "s3:GetLifecycleConfiguration",
          "s3:GetBucketPolicy", "s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock",
          "s3:GetBucketVersioning", "s3:PutBucketVersioning",
          "s3:GetEncryptionConfiguration", "s3:PutEncryptionConfiguration",
          "s3:GetBucketTagging", "s3:PutBucketTagging"
        ]
        Resource = "arn:${local.partition}:s3:::cloudforge-*"
      },
      {
        Sid       = "CreateTaggedDatabases"
        Effect    = "Allow"
        Action    = ["rds:CreateDBInstance", "rds:CreateDBSubnetGroup", "rds:AddTagsToResource"]
        Resource  = ["${local.rds_arn}:db:cloudforge-*", "${local.rds_arn}:subgrp:cloudforge-*"]
        Condition = local.request_managed
      },
      {
        Sid       = "ManageTaggedDatabases"
        Effect    = "Allow"
        Action    = ["rds:DeleteDBInstance", "rds:DeleteDBSubnetGroup", "rds:ModifyDBInstance", "rds:ModifyDBSubnetGroup"]
        Resource  = ["${local.rds_arn}:db:cloudforge-*", "${local.rds_arn}:subgrp:cloudforge-*"]
        Condition = local.resource_managed
      },
      {
        Sid      = "UpdateManagedDatabaseTags"
        Effect   = "Allow"
        Action   = ["rds:AddTagsToResource", "rds:RemoveTagsFromResource"]
        Resource = ["${local.rds_arn}:db:cloudforge-*", "${local.rds_arn}:subgrp:cloudforge-*"]
        Condition = {
          StringEquals                             = local.resource_managed.StringEquals
          "ForAllValues:StringNotEqualsIgnoreCase" = { "aws:TagKeys" = "CloudForge" }
        }
      },
      {
        Sid      = "ReadDatabaseTags"
        Effect   = "Allow"
        Action   = "rds:ListTagsForResource"
        Resource = ["${local.rds_arn}:db:cloudforge-*", "${local.rds_arn}:subgrp:cloudforge-*"]
      },
      {
        Sid      = "CreateFinalDatabaseSnapshot"
        Effect   = "Allow"
        Action   = ["rds:CreateDBSnapshot", "rds:AddTagsToResource"]
        Resource = "${local.rds_arn}:snapshot:cloudforge-final-*"
      }
    ]
  })
}

# Keep EKS in a separate managed policy to stay within the IAM policy size limit.
resource "aws_iam_policy" "eks_provisioning" {
  name        = "cloudforge-eks-provisioning"
  description = "Manages CloudForge EKS clusters and their dedicated IAM roles."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid       = "CreateTaggedClusters"
        Effect    = "Allow"
        Action    = "eks:CreateCluster"
        Resource  = "*"
        Condition = { StringEquals = merge(local.request_managed.StringEquals, { "aws:RequestedRegion" = var.aws_region }) }
      },
      {
        Sid       = "CreateTaggedNodeGroups"
        Effect    = "Allow"
        Action    = "eks:CreateNodegroup"
        Resource  = "${local.eks_arn}:cluster/cloudforge-*"
        Condition = { StringEquals = merge(local.request_managed.StringEquals, local.resource_managed.StringEquals) }
      },
      {
        Sid      = "ReadEKSResources"
        Effect   = "Allow"
        Action   = ["eks:DescribeCluster", "eks:DescribeNodegroup", "eks:ListTagsForResource", "eks:DescribeUpdate"]
        Resource = ["${local.eks_arn}:cluster/cloudforge-*", "${local.eks_arn}:nodegroup/cloudforge-*/*/*"]
      },
      {
        Sid       = "ManageTaggedEKSResources"
        Effect    = "Allow"
        Action    = ["eks:DeleteCluster", "eks:DeleteNodegroup", "eks:UpdateClusterConfig", "eks:UpdateClusterVersion", "eks:UpdateNodegroupConfig", "eks:UpdateNodegroupVersion"]
        Resource  = ["${local.eks_arn}:cluster/cloudforge-*", "${local.eks_arn}:nodegroup/cloudforge-*/*/*"]
        Condition = local.resource_managed
      },
      {
        Sid       = "TagEKSResourcesDuringCreation"
        Effect    = "Allow"
        Action    = "eks:TagResource"
        Resource  = ["${local.eks_arn}:cluster/cloudforge-*", "${local.eks_arn}:nodegroup/cloudforge-*/*/*"]
        Condition = local.request_managed
      },
      {
        Sid       = "CreateEKSServiceLinkedRoles"
        Effect    = "Allow"
        Action    = "iam:CreateServiceLinkedRole"
        Resource  = ["${local.iam_role}/aws-service-role/eks.amazonaws.com/AWSServiceRoleForAmazonEKS", "${local.iam_role}/aws-service-role/eks-nodegroup.amazonaws.com/AWSServiceRoleForAmazonEKSNodegroup"]
        Condition = { StringEquals = { "iam:AWSServiceName" = ["eks.amazonaws.com", "eks-nodegroup.amazonaws.com"] } }
      },
      {
        Sid       = "CreateTaggedEKSRoles"
        Effect    = "Allow"
        Action    = ["iam:CreateRole", "iam:TagRole"]
        Resource  = [for role in local.eks_roles : role.arn]
        Condition = local.request_managed
      },
      {
        Sid      = "ReadGeneratedEKSRoles"
        Effect   = "Allow"
        Action   = ["iam:GetRole", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies", "iam:ListInstanceProfilesForRole", "iam:ListRoleTags"]
        Resource = [for role in local.eks_roles : role.arn]
      },
      {
        Sid       = "DeleteTaggedEKSRoles"
        Effect    = "Allow"
        Action    = "iam:DeleteRole"
        Resource  = [for role in local.eks_roles : role.arn]
        Condition = local.resource_managed
      },
      {
        Sid       = "PassTaggedEKSRolesOnlyToEKS"
        Effect    = "Allow"
        Action    = "iam:PassRole"
        Resource  = [for role in local.eks_roles : role.arn]
        Condition = { StringEquals = { "iam:PassedToService" = ["eks.amazonaws.com", "ec2.amazonaws.com"] } }
      }
      ], [for kind, role in local.eks_roles : {
        Sid      = "ManageApprovedEKSPolicies${title(kind)}"
        Effect   = "Allow"
        Action   = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
        Resource = role.arn
        Condition = {
          ArnEquals    = { "iam:PolicyARN" = [for name in role.policies : "${local.aws_policy}/${name}"] }
          StringEquals = local.resource_managed.StringEquals
        }
    }])
  })
}

resource "aws_iam_role_policy_attachment" "provisioner_attach_eks" {
  role       = aws_iam_role.terraform_provisioner.name
  policy_arn = aws_iam_policy.eks_provisioning.arn
}
