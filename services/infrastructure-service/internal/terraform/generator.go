package terraform

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

const (
	awsProvider = "~> 6.62"

	resourceVPC = "aws_vpc"
	resourceEC2 = "aws_ec2"
	resourceS3  = "aws_s3"
	resourceRDS = "aws_rds"
	resourceEKS = "aws_eks"
	resourceLB  = "aws_lb"
)

var (
	rdsEnginePattern = regexp.MustCompile(
		`^(postgres|mysql|mariadb)$`,
	)
	s3BucketNamePattern = regexp.MustCompile(
		`^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$`,
	)

	ec2InstanceTypePattern = regexp.MustCompile(
		`^[a-z0-9][a-z0-9.-]{1,31}$`,
	)

	amiPattern = regexp.MustCompile(
		`^(ami-[a-zA-Z0-9]+|resolve:ssm:/[A-Za-z0-9._/@+=,:-]+)$`,
	)

	subnetPattern = regexp.MustCompile(
		`^subnet-[a-zA-Z0-9]+$`,
	)

	securityGroupPattern = regexp.MustCompile(
		`^sg-[a-zA-Z0-9]+$`,
	)
)

type Generator struct {
	WorkspaceRoot string
	StateBucket   string
}

type GeneratedWorkspace struct {
	Directory string
	Files     []string
}

func NewGenerator(workspaceRoot, stateBucket string) *Generator {
	return &Generator{
		WorkspaceRoot: workspaceRoot,
		StateBucket:   strings.TrimSpace(stateBucket),
	}
}

func (g *Generator) Generate(
	resource model.InfrastructureResource,
) (GeneratedWorkspace, error) {
	if resource.ID == uuid.Nil {
		return GeneratedWorkspace{}, errors.New(
			"resource ID cannot be empty",
		)
	}

	if resource.Provider != model.ProviderAWS {
		return GeneratedWorkspace{}, errors.New(
			"only AWS resources are supported",
		)
	}

	if strings.TrimSpace(resource.Region) == "" {
		return GeneratedWorkspace{}, errors.New(
			"region cannot be empty",
		)
	}

	if strings.TrimSpace(g.WorkspaceRoot) == "" {
		return GeneratedWorkspace{}, errors.New(
			"terraform workspace root cannot be empty",
		)
	}

	switch resource.ResourceType {
	case resourceVPC, resourceEC2, resourceS3, resourceRDS, resourceEKS, resourceLB:
	default:
		return GeneratedWorkspace{}, fmt.Errorf(
			"unsupported resource type: %s",
			resource.ResourceType,
		)
	}

	workspace := filepath.Join(
		g.WorkspaceRoot,
		resource.ID.String(),
	)

	files := map[string]string{
		"versions.tf":  g.versionsFile(),
		"variables.tf": g.variablesFile(resource),
		"outputs.tf":   g.outputsFile(),
	}

	main, err := g.mainFile(resource)
	if err != nil {
		return GeneratedWorkspace{}, err
	}

	files["main.tf"] = main

	if g.StateBucket != "" {
		files["backend.tf"] = g.backendFile(resource)
	}

	for name, content := range files {
		if err := writeWorkspaceFile(
			workspace,
			name,
			content,
		); err != nil {
			return GeneratedWorkspace{}, err
		}
	}

	names := make([]string, 0, len(files))

	for name := range files {
		names = append(names, name)
	}

	sort.Strings(names)

	return GeneratedWorkspace{
		Directory: workspace,
		Files:     names,
	}, nil
}

func (g *Generator) versionsFile() string {
	return fmt.Sprintf(`terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "%s"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      ManagedBy       = "cloudforge-ai"
      CloudForge      = "true"
      ResourceManaged = "terraform"
    }
  }
}
`, awsProvider)
}

func (g *Generator) backendFile(
	resource model.InfrastructureResource,
) string {
	return fmt.Sprintf(`terraform {
  backend "s3" {
    bucket       = %q
    key          = "cloudforge/resources/%s/terraform.tfstate"
    region       = %q
    encrypt      = true
    use_lockfile = true
  }
}
`, g.StateBucket, resource.ID.String(), resource.Region)
}

func (g *Generator) variablesFile(
	resource model.InfrastructureResource,
) string {
	return fmt.Sprintf(`variable "aws_region" {
  description = "AWS region for this CloudForge resource."
  type        = string
  default     = %q
}

variable "resource_name" {
  description = "CloudForge resource name."
  type        = string
  default     = %q
}

variable "resource_id" {
  description = "CloudForge resource UUID."
  type        = string
  default     = %q
}
`, resource.Region, hclEscape(resource.Name), resource.ID.String())
}

func (g *Generator) outputsFile() string {
	return `output "resource_id" {
  description = "Managed AWS resource identifier."
  value       = local.resource_id
}

output "resource_type" {
  description = "CloudForge resource type."
  value       = local.resource_type
}
`
}

func (g *Generator) mainFile(
	resource model.InfrastructureResource,
) (string, error) {
	switch resource.ResourceType {
	case resourceVPC:
		return g.vpcFile(resource)
	case resourceEC2:
		return g.ec2File(resource)
	case resourceS3:
		return g.s3File(resource)
	case resourceRDS:
		return g.rdsFile(resource)
	case resourceEKS:
		return g.eksFile(resource)
	case resourceLB:
		return g.lbFile(resource)
	default:
		return "", fmt.Errorf(
			"unsupported resource type: %s",
			resource.ResourceType,
		)
	}
}

func (g *Generator) vpcFile(
	resource model.InfrastructureResource,
) (string, error) {
	cidr, ok := stringValue(
		resource.Configuration,
		"cidr_block",
	)

	if !ok {
		return "", errors.New(
			"aws_vpc requires configuration.cidr_block",
		)
	}

	_, network, err := net.ParseCIDR(cidr)
	if err != nil || network == nil {
		return "", errors.New(
			"configuration.cidr_block must be a valid CIDR",
		)
	}

	if network.IP.To4() == nil {
		return "", errors.New(
			"configuration.cidr_block must be an IPv4 CIDR",
		)
	}

	enableDNSHostnames := boolValue(
		resource.Configuration,
		"enable_dns_hostnames",
		true,
	)

	enableDNSSupport := boolValue(
		resource.Configuration,
		"enable_dns_support",
		true,
	)

	tags, err := tagsValue(resource.Configuration)
	if err != nil {
		return "", err
	}

	return fmt.Sprintf(`locals {
  resource_id   = var.resource_id
  resource_type = "aws_vpc"
}

resource "aws_vpc" "this" {
  cidr_block           = %q
  enable_dns_hostnames = %t
  enable_dns_support   = %t

  tags = merge(
    {
      Name = var.resource_name
    },
    %s
  )
}

output "vpc_id" {
  description = "Created VPC ID."
  value       = aws_vpc.this.id
}

output "vpc_arn" {
  description = "Created VPC ARN."
  value       = aws_vpc.this.arn
}
`, cidr, enableDNSHostnames, enableDNSSupport, renderTags(tags)), nil
}

func (g *Generator) ec2File(
	resource model.InfrastructureResource,
) (string, error) {
	amiID, ok := stringValue(
		resource.Configuration,
		"ami_id",
	)

	if !ok || !amiPattern.MatchString(amiID) {
		return "", errors.New(
			"aws_ec2 requires a valid configuration.ami_id",
		)
	}

	instanceType, ok := stringValue(
		resource.Configuration,
		"instance_type",
	)

	if !ok || !ec2InstanceTypePattern.MatchString(instanceType) {
		return "", errors.New(
			"aws_ec2 requires a valid configuration.instance_type",
		)
	}

	subnetID, hasSubnet := stringValue(
		resource.Configuration,
		"subnet_id",
	)

	if hasSubnet && subnetID != "" && !subnetPattern.MatchString(subnetID) {
		return "", errors.New(
			"configuration.subnet_id must be a valid subnet ID (subnet-*)",
		)
	}

	associatePublicIP := boolValue(
		resource.Configuration,
		"associate_public_ip_address",
		false,
	)

	keyName, _ := stringValue(
		resource.Configuration,
		"key_name",
	)

	securityGroups, err := stringSliceValue(
		resource.Configuration,
		"security_group_ids",
	)

	if err != nil {
		return "", err
	}

	for _, securityGroup := range securityGroups {
		if !securityGroupPattern.MatchString(securityGroup) {
			return "", fmt.Errorf(
				"invalid security group ID: %s",
				securityGroup,
			)
		}
	}

	tags, err := tagsValue(resource.Configuration)
	if err != nil {
		return "", err
	}

	var builder strings.Builder

	builder.WriteString(fmt.Sprintf(`locals {
  resource_id   = var.resource_id
  resource_type = "aws_ec2"
}

resource "aws_instance" "this" {
  ami                         = %q
  instance_type               = %q
  associate_public_ip_address = %t
`, amiID, instanceType, associatePublicIP))

	if hasSubnet && subnetID != "" {
		builder.WriteString(
			fmt.Sprintf(
				"  subnet_id                   = %q\n",
				subnetID,
			),
		)
	}

	if keyName != "" {
		builder.WriteString(
			fmt.Sprintf(
				"  key_name = %q\n",
				keyName,
			),
		)
	}

	if len(securityGroups) > 0 {
		builder.WriteString(
			"  vpc_security_group_ids = [\n",
		)

		for _, securityGroup := range securityGroups {
			builder.WriteString(
				fmt.Sprintf(
					"    %q,\n",
					securityGroup,
				),
			)
		}

		builder.WriteString("  ]\n")
	}

	builder.WriteString(
		fmt.Sprintf(`
  tags = merge(
    {
      Name = var.resource_name
    },
    %s
  )
}

output "instance_id" {
  description = "Created EC2 instance ID."
  value       = aws_instance.this.id
}

output "instance_arn" {
  description = "Created EC2 instance ARN."
  value       = aws_instance.this.arn
}

output "private_ip" {
  description = "Private IP assigned to the instance."
  value       = aws_instance.this.private_ip
}
`, renderTags(tags)),
	)

	return builder.String(), nil
}

func (g *Generator) s3File(
	resource model.InfrastructureResource,
) (string, error) {
	bucket, ok := stringValue(
		resource.Configuration,
		"bucket",
	)

	if !ok || !s3BucketNamePattern.MatchString(bucket) {
		return "", errors.New(
			"aws_s3 requires a valid configuration.bucket",
		)
	}

	forceDestroy := boolValue(
		resource.Configuration,
		"force_destroy",
		false,
	)

	versioning := boolValue(
		resource.Configuration,
		"versioning",
		true,
	)

	tags, err := tagsValue(resource.Configuration)
	if err != nil {
		return "", err
	}

	return fmt.Sprintf(`locals {
  resource_id   = var.resource_id
  resource_type = "aws_s3"
}

resource "aws_s3_bucket" "this" {
  bucket        = %q
  force_destroy = %t

  tags = merge(
    {
      Name = var.resource_name
    },
    %s
  )
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = %q
  }
}

output "bucket_name" {
  description = "Created S3 bucket name."
  value       = aws_s3_bucket.this.id
}

output "bucket_arn" {
  description = "Created S3 bucket ARN."
  value       = aws_s3_bucket.this.arn
}
`, bucket, forceDestroy, renderTags(tags), versioningStatus(versioning)), nil
}

func versioningStatus(enabled bool) string {
	if enabled {
		return "Enabled"
	}

	return "Suspended"
}

func (g *Generator) rdsFile(
	resource model.InfrastructureResource,
) (string, error) {
	engine, ok := stringValue(resource.Configuration, "engine")
	if !ok {
		engine = "postgres"
	}
	if !rdsEnginePattern.MatchString(engine) {
		return "", fmt.Errorf("unsupported or invalid database engine: %s", engine)
	}

	engineVersion, ok := stringValue(resource.Configuration, "engine_version")
	if !ok {
		if engine == "postgres" {
			engineVersion = "16.3"
		} else {
			engineVersion = "8.0"
		}
	}

	instanceClass, ok := stringValue(resource.Configuration, "instance_class")
	if !ok {
		instanceClass = "db.t4g.micro"
	}

	allocatedStorage := intValue(resource.Configuration, "allocated_storage", 20)
	if allocatedStorage < 20 || allocatedStorage > 1000 {
		return "", errors.New("allocated_storage must be between 20 and 1000 GB")
	}

	databaseName, ok := stringValue(resource.Configuration, "database_name")
	if !ok {
		databaseName = "cloudforge"
	}

	username, ok := stringValue(resource.Configuration, "username")
	if !ok {
		username = "cloudforge_admin"
	}

	password, ok := stringValue(resource.Configuration, "password")
	if !ok {
		generated, err := generateSecurePassword()
		if err != nil {
			return "", fmt.Errorf("generate RDS master password: %w", err)
		}
		password = generated
	}

	subnetIDs, err := stringSliceValue(resource.Configuration, "subnet_ids")
	if err != nil {
		return "", err
	}

	skipFinalSnapshot := boolValue(resource.Configuration, "skip_final_snapshot", true)
	multiAZ := boolValue(resource.Configuration, "multi_az", false)

	tags, err := tagsValue(resource.Configuration)
	if err != nil {
		return "", err
	}

	var builder strings.Builder
	builder.WriteString(`locals {
  resource_id   = var.resource_id
  resource_type = "aws_rds"
}
`)

	builder.WriteString(fmt.Sprintf(`
variable "db_master_password" {
  description = "Master password for the CloudForge managed RDS instance."
  type        = string
  sensitive   = true
  default     = %q
}
`, hclEscape(password)))

	if len(subnetIDs) >= 2 {
		builder.WriteString(fmt.Sprintf(`
resource "aws_db_subnet_group" "this" {
  name        = "cloudforge-db-subnet-${var.resource_name}"
  description = "Subnet group for CloudForge managed RDS instance"
  subnet_ids  = %s

  tags = merge(
    {
      Name = var.resource_name
    },
    %s
  )
}
`, renderStringList(subnetIDs), renderTags(tags)))
	}

	builder.WriteString(fmt.Sprintf(`
resource "aws_db_instance" "this" {
  identifier          = replace(lower(var.resource_name), "_", "-")
  allocated_storage   = %d
  engine              = %q
  engine_version      = %q
  instance_class      = %q
  db_name             = %q
  username            = %q
  password            = var.db_master_password
  skip_final_snapshot = %t
  multi_az            = %t
`, allocatedStorage, engine, engineVersion, instanceClass, databaseName, username, skipFinalSnapshot, multiAZ))

	if len(subnetIDs) >= 2 {
		builder.WriteString("  db_subnet_group_name = aws_db_subnet_group.this.name\n")
	}

	builder.WriteString(fmt.Sprintf(`
  tags = merge(
    {
      Name = var.resource_name
    },
    %s
  )
}

output "db_instance_id" {
  description = "Created RDS instance identifier."
  value       = aws_db_instance.this.id
}

output "db_instance_endpoint" {
  description = "Connection endpoint for the RDS database."
  value       = aws_db_instance.this.endpoint
}

output "db_instance_address" {
  description = "Hostname of the RDS instance."
  value       = aws_db_instance.this.address
}

output "db_instance_port" {
  description = "Database listening port."
  value       = aws_db_instance.this.port
}
`, renderTags(tags)))

	return builder.String(), nil
}

func (g *Generator) eksFile(
	resource model.InfrastructureResource,
) (string, error) {
	clusterVersion, ok := stringValue(resource.Configuration, "cluster_version")
	if !ok {
		clusterVersion = "1.30"
	}

	subnetIDs, err := stringSliceValue(resource.Configuration, "subnet_ids")
	if err != nil {
		return "", err
	}
	if len(subnetIDs) < 2 {
		return "", errors.New("aws_eks requires at least two subnet_ids across multiple availability zones")
	}

	nodeInstanceTypes, err := stringSliceValue(resource.Configuration, "node_instance_types")
	if err != nil {
		return "", err
	}
	if len(nodeInstanceTypes) == 0 {
		nodeInstanceTypes = []string{"t3.medium"}
	}

	desiredCapacity := intValue(resource.Configuration, "desired_capacity", 2)
	minCapacity := intValue(resource.Configuration, "min_capacity", 1)
	maxCapacity := intValue(resource.Configuration, "max_capacity", 4)

	tags, err := tagsValue(resource.Configuration)
	if err != nil {
		return "", err
	}

	return fmt.Sprintf(`locals {
  resource_id   = var.resource_id
  resource_type = "aws_eks"
}

resource "aws_iam_role" "cluster" {
  name = "cloudforge-eks-cluster-role-${var.resource_name}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
    }]
  })

  tags = %s
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.cluster.name
}

resource "aws_eks_cluster" "this" {
  name     = replace(lower(var.resource_name), "_", "-")
  role_arn = aws_iam_role.cluster.arn
  version  = %q

  vpc_config {
    subnet_ids = %s
  }

  depends_on = [
    aws_iam_role_policy_attachment.cluster_policy
  ]

  tags = merge(
    {
      Name = var.resource_name
    },
    %s
  )
}

resource "aws_iam_role" "node" {
  name = "cloudforge-eks-node-role-${var.resource_name}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = %s
}

resource "aws_iam_role_policy_attachment" "worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.node.name
}

resource "aws_iam_role_policy_attachment" "cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.node.name
}

resource "aws_iam_role_policy_attachment" "registry_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.node.name
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "default-pool"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = %s
  instance_types  = %s

  scaling_config {
    desired_size = %d
    min_size     = %d
    max_size     = %d
  }

  depends_on = [
    aws_iam_role_policy_attachment.worker_node_policy,
    aws_iam_role_policy_attachment.cni_policy,
    aws_iam_role_policy_attachment.registry_policy
  ]

  tags = merge(
    {
      Name = "${var.resource_name}-nodepool"
    },
    %s
  )
}

output "cluster_id" {
  description = "EKS Cluster ID."
  value       = aws_eks_cluster.this.id
}

output "cluster_endpoint" {
  description = "Kubernetes API server endpoint."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_arn" {
  description = "EKS Cluster ARN."
  value       = aws_eks_cluster.this.arn
}

output "cluster_version" {
  description = "Kubernetes version."
  value       = aws_eks_cluster.this.version
}
`, renderTags(tags), clusterVersion, renderStringList(subnetIDs), renderTags(tags), renderTags(tags), renderStringList(subnetIDs), renderStringList(nodeInstanceTypes), desiredCapacity, minCapacity, maxCapacity, renderTags(tags)), nil
}

func (g *Generator) lbFile(
	resource model.InfrastructureResource,
) (string, error) {
	lbType, ok := stringValue(resource.Configuration, "load_balancer_type")
	if !ok {
		lbType = "application"
	}

	subnetIDs, err := stringSliceValue(resource.Configuration, "subnet_ids")
	if err != nil {
		return "", err
	}
	if len(subnetIDs) < 2 {
		return "", errors.New("aws_lb requires at least two subnet_ids across availability zones")
	}

	securityGroups, err := stringSliceValue(resource.Configuration, "security_groups")
	if err != nil {
		return "", err
	}

	internal := boolValue(resource.Configuration, "internal", false)
	port := intValue(resource.Configuration, "port", 80)
	protocol, ok := stringValue(resource.Configuration, "protocol")
	if !ok {
		protocol = "HTTP"
	}

	tags, err := tagsValue(resource.Configuration)
	if err != nil {
		return "", err
	}

	var builder strings.Builder
	builder.WriteString(fmt.Sprintf(`locals {
  resource_id   = var.resource_id
  resource_type = "aws_lb"
}

resource "aws_lb" "this" {
  name               = replace(lower(var.resource_name), "_", "-")
  internal           = %t
  load_balancer_type = %q
  subnets            = %s
`, internal, lbType, renderStringList(subnetIDs)))

	if len(securityGroups) > 0 {
		builder.WriteString(fmt.Sprintf("  security_groups    = %s\n", renderStringList(securityGroups)))
	}

	builder.WriteString(fmt.Sprintf(`
  tags = merge(
    {
      Name = var.resource_name
    },
    %s
  )
}

resource "aws_lb_target_group" "this" {
  name     = "tg-${replace(lower(var.resource_name), "_", "-")}"
  port     = %d
  protocol = %q
  vpc_id   = var.resource_id

  tags = %s
}

resource "aws_lb_listener" "this" {
  load_balancer_arn = aws_lb.this.arn
  port              = %d
  protocol          = %q

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

output "lb_id" {
  description = "Load Balancer ID."
  value       = aws_lb.this.id
}

output "lb_arn" {
  description = "Load Balancer ARN."
  value       = aws_lb.this.arn
}

output "lb_dns_name" {
  description = "Public or internal DNS name of the Load Balancer."
  value       = aws_lb.this.dns_name
}

output "target_group_arn" {
  description = "Target Group ARN for service attachments."
  value       = aws_lb_target_group.this.arn
}
`, renderTags(tags), port, protocol, renderTags(tags), port, protocol))

	return builder.String(), nil
}

func intValue(
	configuration map[string]any,
	key string,
	defaultValue int,
) int {
	value, exists := configuration[key]
	if !exists {
		return defaultValue
	}
	switch v := value.(type) {
	case int:
		return v
	case int64:
		return int(v)
	case float64:
		return int(v)
	default:
		return defaultValue
	}
}

func renderStringList(items []string) string {
	if len(items) == 0 {
		return "[]"
	}
	parts := make([]string, len(items))
	for i, item := range items {
		parts[i] = fmt.Sprintf("%q", item)
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

func stringValue(
	configuration map[string]any,
	key string,
) (string, bool) {
	value, exists := configuration[key]

	if !exists {
		return "", false
	}

	text, ok := value.(string)

	if !ok {
		return "", false
	}

	text = strings.TrimSpace(text)

	if text == "" {
		return "", false
	}

	return hclEscape(text), true
}

// hclEscape neutralizes Terraform's string-template interpolation syntax
// ("${...}" and "%{...}") so user-supplied values embedded as HCL string
// literals cannot trigger function evaluation (e.g. file(), templatefile())
// at terraform plan/apply time. Go's %q only escapes quotes/backslashes,
// not these HCL-specific sequences.
func hclEscape(s string) string {
	s = strings.ReplaceAll(s, "$", "$$")
	s = strings.ReplaceAll(s, "%", "%%")
	return s
}

func generateSecurePassword() (string, error) {
	const (
		charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
		length  = 32
	)

	password := make([]byte, length)

	for i := range password {
		n, err := rand.Int(rand.Reader, big.NewInt(int64(len(charset))))
		if err != nil {
			return "", err
		}

		password[i] = charset[n.Int64()]
	}

	return string(password), nil
}

func boolValue(
	configuration map[string]any,
	key string,
	defaultValue bool,
) bool {
	value, exists := configuration[key]

	if !exists {
		return defaultValue
	}

	boolean, ok := value.(bool)

	if !ok {
		return defaultValue
	}

	return boolean
}

func stringSliceValue(
	configuration map[string]any,
	key string,
) ([]string, error) {
	value, exists := configuration[key]

	if !exists {
		return nil, nil
	}

	raw, ok := value.([]any)

	if ok {
		result := make([]string, 0, len(raw))

		for _, item := range raw {
			text, ok := item.(string)

			if !ok || strings.TrimSpace(text) == "" {
				return nil, fmt.Errorf(
					"%s must contain only non-empty strings",
					key,
				)
			}

			result = append(
				result,
				hclEscape(strings.TrimSpace(text)),
			)
		}

		return result, nil
	}

	rawStrings, ok := value.([]string)

	if !ok {
		return nil, fmt.Errorf(
			"%s must be an array of strings",
			key,
		)
	}

	result := make([]string, 0, len(rawStrings))

	for _, item := range rawStrings {
		item = strings.TrimSpace(item)

		if item == "" {
			return nil, fmt.Errorf(
				"%s must contain only non-empty strings",
				key,
			)
		}

		result = append(result, hclEscape(item))
	}

	return result, nil
}

func tagsValue(
	configuration map[string]any,
) (map[string]string, error) {
	value, exists := configuration["tags"]

	if !exists {
		return map[string]string{}, nil
	}

	raw, ok := value.(map[string]any)

	if ok {
		result := make(map[string]string, len(raw))

		for key, value := range raw {
			text, ok := value.(string)

			if !ok {
				return nil, fmt.Errorf(
					"configuration.tags[%s] must be a string",
					key,
				)
			}

			result[hclEscape(key)] = hclEscape(text)
		}

		return result, nil
	}

	rawStrings, ok := value.(map[string]string)

	if !ok {
		return nil, errors.New(
			"configuration.tags must be an object",
		)
	}

	result := make(map[string]string, len(rawStrings))

	for key, value := range rawStrings {
		result[hclEscape(key)] = hclEscape(value)
	}

	return result, nil
}

func renderTags(tags map[string]string) string {
	if len(tags) == 0 {
		return "{}"
	}

	keys := make([]string, 0, len(tags))

	for key := range tags {
		keys = append(keys, key)
	}

	sort.Strings(keys)

	var builder strings.Builder

	builder.WriteString("{\n")

	for _, key := range keys {
		builder.WriteString(
			fmt.Sprintf(
				"      %q = %q\n",
				key,
				tags[key],
			),
		)
	}

	builder.WriteString("    }")

	return builder.String()
}

func writeWorkspaceFile(
	workspace string,
	name string,
	content string,
) error {
	if strings.Contains(name, "/") ||
		strings.Contains(name, "\\") ||
		name == "." ||
		name == ".." {
		return fmt.Errorf(
			"invalid terraform filename: %s",
			name,
		)
	}

	if err := os.MkdirAll(workspace, 0750); err != nil {
		return fmt.Errorf(
			"create terraform workspace: %w",
			err,
		)
	}

	path := filepath.Join(workspace, name)

	cleanWorkspace := filepath.Clean(workspace)
	cleanPath := filepath.Clean(path)

	if !strings.HasPrefix(
		cleanPath,
		cleanWorkspace+string(filepath.Separator),
	) {
		return errors.New(
			"terraform workspace path traversal rejected",
		)
	}

	if err := os.WriteFile(
		cleanPath,
		[]byte(content),
		0600,
	); err != nil {
		return fmt.Errorf(
			"write terraform file %s: %w",
			name,
			err,
		)
	}

	return nil
}

func MarshalConfiguration(
	configuration map[string]any,
) ([]byte, error) {
	return json.Marshal(configuration)
}
