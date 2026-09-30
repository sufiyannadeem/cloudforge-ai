package terraform

import (
	"encoding/json"
	"errors"
	"fmt"
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
	terraformVersion = "1.16.4"
	awsProvider      = "~> 6.62"

	resourceVPC = "aws_vpc"
	resourceEC2 = "aws_ec2"
	resourceS3  = "aws_s3"
)

var (
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
	case resourceVPC, resourceEC2, resourceS3:
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
  required_version = "=%s"

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
`, terraformVersion, awsProvider)
}

func (g *Generator) backendFile(
	resource model.InfrastructureResource,
) string {
	return fmt.Sprintf(`terraform {
  backend "s3" {
    bucket       = %q
    key          = "cloudforge/resources/%s/terraform.tfstate"
    region       = var.aws_region
    encrypt      = true
    use_lockfile = true
  }
}
`, g.StateBucket, resource.ID.String())
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
`, resource.Region, resource.Name, resource.ID.String())
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

	subnetID, ok := stringValue(
		resource.Configuration,
		"subnet_id",
	)

	if !ok || !subnetPattern.MatchString(subnetID) {
		return "", errors.New(
			"aws_ec2 requires a valid configuration.subnet_id",
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
  subnet_id                   = %q
  associate_public_ip_address = %t
`, amiID, instanceType, subnetID, associatePublicIP))

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

	return text, true
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
				strings.TrimSpace(text),
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

		result = append(result, item)
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

			result[key] = text
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
		result[key] = value
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
