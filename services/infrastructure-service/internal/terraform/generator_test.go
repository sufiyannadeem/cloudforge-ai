package terraform

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func TestGeneratorAWSS3(t *testing.T) {
	root := t.TempDir()

	generator := NewGenerator(
		root,
		"cloudforge-ai-test-state",
	)

	resource := model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         "Test Bucket",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_s3",
		Configuration: map[string]any{
			"bucket":     "cloudforge-test-example",
			"versioning": true,
			"tags": map[string]any{
				"Team": "platform",
			},
		},
	}

	result, err := generator.Generate(resource)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if result.Directory == "" {
		t.Fatal("expected workspace directory")
	}

	mainPath := filepath.Join(
		result.Directory,
		"main.tf",
	)

	data, err := os.ReadFile(mainPath)
	if err != nil {
		t.Fatalf("read generated main.tf: %v", err)
	}

	content := string(data)

	required := []string{
		`resource "aws_s3_bucket" "this"`,
		`resource "aws_s3_bucket_public_access_block" "this"`,
		`resource "aws_s3_bucket_versioning" "this"`,
		`resource "aws_s3_bucket_server_side_encryption_configuration" "this"`,
	}

	for _, value := range required {
		if !strings.Contains(content, value) {
			t.Fatalf(
				"expected generated HCL to contain %q",
				value,
			)
		}
	}

	if !strings.Contains(
		string(mustReadFile(t, filepath.Join(
			result.Directory,
			"backend.tf",
		))),
		`key          = "cloudforge/resources/`,
	) {
		t.Fatal("expected isolated S3 backend state key")
	}
}

func TestGeneratorRejectsUnsupportedResource(t *testing.T) {
	generator := NewGenerator(
		t.TempDir(),
		"",
	)

	resource := model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         "Unsupported",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_unsupported",
	}

	_, err := generator.Generate(resource)

	if err == nil {
		t.Fatal("expected unsupported resource type error")
	}
}

func TestGeneratorAWSRDS(t *testing.T) {
	root := t.TempDir()
	generator := NewGenerator(root, "")

	resource := model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         "Test-RDS",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_rds",
		Configuration: map[string]any{
			"engine":              "postgres",
			"engine_version":      "16.3",
			"instance_class":      "db.t4g.micro",
			"allocated_storage":   20,
			"skip_final_snapshot": false,
			"database_name":       "cloudforge_test",
			"subnet_ids":          []string{"subnet-11111111", "subnet-22222222"},
		},
	}

	result, err := generator.Generate(resource)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	mainPath := filepath.Join(result.Directory, "main.tf")
	data, err := os.ReadFile(mainPath)
	if err != nil {
		t.Fatalf("read generated main.tf: %v", err)
	}

	content := string(data)
	if !strings.Contains(content, `resource "aws_db_instance" "this"`) {
		t.Error("expected aws_db_instance resource")
	}
	if !strings.Contains(content, `resource "aws_db_subnet_group" "this"`) {
		t.Error("expected aws_db_subnet_group resource")
	}
	if !strings.Contains(content, `engine_version = "16.3"`) ||
		!strings.Contains(content, `final_snapshot_identifier = "cloudforge-final-`+resource.ID.String()+`"`) {
		t.Fatal("explicit version or final snapshot setting was not preserved")
	}
	if !strings.Contains(content, `output "db_instance_endpoint"`) {
		t.Error("expected db_instance_endpoint output")
	}
}

func TestGeneratorAWSEKS(t *testing.T) {
	root := t.TempDir()
	generator := NewGenerator(root, "")

	resource := model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         "Test-EKS",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_eks",
		Configuration: map[string]any{
			"subnet_ids":          []string{"subnet-11111111", "subnet-22222222"},
			"node_instance_types": []string{"t3.medium"},
			"desired_capacity":    2,
		},
	}

	result, err := generator.Generate(resource)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	mainPath := filepath.Join(result.Directory, "main.tf")
	data, err := os.ReadFile(mainPath)
	if err != nil {
		t.Fatalf("read generated main.tf: %v", err)
	}

	content := string(data)
	if !strings.Contains(content, "version  = null") {
		t.Fatal("EKS should use its service default when no version is supplied")
	}
	if !strings.Contains(content, `resource "aws_eks_cluster" "this"`) {
		t.Error("expected aws_eks_cluster resource")
	}
	if !strings.Contains(content, `resource "aws_eks_node_group" "this"`) {
		t.Error("expected aws_eks_node_group resource")
	}
	if !strings.Contains(content, `output "cluster_endpoint"`) {
		t.Error("expected cluster_endpoint output")
	}
}

func TestGeneratorAWSLB(t *testing.T) {
	root := t.TempDir()
	generator := NewGenerator(root, "")

	resource := model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         "Test-LB",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_lb",
		Configuration: map[string]any{
			"load_balancer_type": "application",
			"subnet_ids":         []string{"subnet-11111111", "subnet-22222222"},
			"port":               80,
			"protocol":           "HTTP",
		},
	}

	result, err := generator.Generate(resource)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	mainPath := filepath.Join(result.Directory, "main.tf")
	data, err := os.ReadFile(mainPath)
	if err != nil {
		t.Fatalf("read generated main.tf: %v", err)
	}

	content := string(data)
	if !strings.Contains(content, `resource "aws_lb" "this"`) {
		t.Error("expected aws_lb resource")
	}
	if !strings.Contains(content, `resource "aws_lb_target_group" "this"`) {
		t.Error("expected aws_lb_target_group resource")
	}
	if !strings.Contains(content, `output "lb_dns_name"`) {
		t.Error("expected lb_dns_name output")
	}
}

func TestGeneratorRejectsInvalidS3Bucket(t *testing.T) {
	generator := NewGenerator(
		t.TempDir(),
		"",
	)

	resource := model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         "Invalid Bucket",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_s3",
		Configuration: map[string]any{
			"bucket": "INVALID_BUCKET",
		},
	}

	_, err := generator.Generate(resource)

	if err == nil {
		t.Fatal("expected invalid bucket error")
	}
}

func mustReadFile(
	t *testing.T,
	path string,
) []byte {
	t.Helper()

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}

	return data
}

func TestGeneratorEscapesTerraformInterpolationInUserInput(t *testing.T) {
	root := t.TempDir()
	generator := NewGenerator(root, "")

	resource := model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         `evil-${file("/etc/shadow")}`,
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_vpc",
		Configuration: map[string]any{
			"cidr_block": "10.0.0.0/16",
			"tags": map[string]any{
				"owner": `${templatefile("/etc/passwd", {})}`,
			},
		},
	}

	result, err := generator.Generate(resource)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	variables := string(mustReadFile(t, filepath.Join(result.Directory, "variables.tf")))
	if strings.Contains(variables, `${file("/etc/shadow")}`) {
		t.Fatal("resource name interpolation sequence was not escaped in variables.tf")
	}
	// Go's %q renders the HCL string literal, so inner quotes appear escaped.
	if !strings.Contains(variables, `evil-$${file(\"/etc/shadow\")}`) {
		t.Fatal("expected escaped $$ sequence in variables.tf")
	}

	main := string(mustReadFile(t, filepath.Join(result.Directory, "main.tf")))
	if strings.Contains(main, `${templatefile("/etc/passwd", {})}`) {
		t.Fatal("tag value interpolation sequence was not escaped in main.tf")
	}
}

func TestGeneratorRDSGeneratesRandomSensitivePasswordWhenOmitted(t *testing.T) {
	root := t.TempDir()
	generator := NewGenerator(root, "")

	newResource := func() model.InfrastructureResource {
		return model.InfrastructureResource{
			ID:           uuid.New(),
			Name:         "test-rds",
			Provider:     model.ProviderAWS,
			Region:       "eu-west-1",
			ResourceType: "aws_rds",
			Configuration: map[string]any{
				"engine":            "postgres",
				"allocated_storage": 20,
			},
		}
	}

	first, err := generator.Generate(newResource())
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	second, err := generator.Generate(newResource())
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	firstMain := string(mustReadFile(t, filepath.Join(first.Directory, "main.tf")))
	secondMain := string(mustReadFile(t, filepath.Join(second.Directory, "main.tf")))

	if strings.Contains(firstMain, "CloudForgeSecurePassword123!") {
		t.Fatal("generated RDS config must not contain the legacy hardcoded default password")
	}
	if strings.Contains(firstMain, "engine_version") {
		t.Fatal("RDS should use the provider default when no engine version is supplied")
	}
	if !strings.Contains(firstMain, `sensitive   = true`) {
		t.Fatal("expected db_master_password variable to be marked sensitive")
	}
	if !strings.Contains(firstMain, "password            = var.db_master_password") {
		t.Fatal("expected db_instance password to reference the sensitive variable")
	}

	extractPassword := func(content string) string {
		marker := `variable "db_master_password" {`
		idx := strings.Index(content, marker)
		if idx == -1 {
			t.Fatal("db_master_password variable block not found")
		}
		block := content[idx:]
		defaultIdx := strings.Index(block, `default     = "`)
		if defaultIdx == -1 {
			t.Fatal("default password value not found")
		}
		rest := block[defaultIdx+len(`default     = "`):]
		endIdx := strings.Index(rest, `"`)
		if endIdx == -1 {
			t.Fatal("could not find end of default password value")
		}
		return rest[:endIdx]
	}

	firstPassword := extractPassword(firstMain)
	secondPassword := extractPassword(secondMain)

	if firstPassword == "" || secondPassword == "" {
		t.Fatal("expected non-empty generated passwords")
	}
	if firstPassword == secondPassword {
		t.Fatal("expected distinct randomly generated passwords across resources")
	}
}

func TestBackendRegionIsIndependentOfResourceRegion(t *testing.T) {
	generator := NewGenerator(t.TempDir(), "state-test-bucket")
	generator.StateRegion = "eu-west-1"
	resource := testResource()
	resource.Region = "us-east-1"
	workspace, err := generator.Generate(resource)
	if err != nil {
		t.Fatal(err)
	}
	backend := string(mustReadFile(t, filepath.Join(workspace.Directory, "backend.tf")))
	variables := string(mustReadFile(t, filepath.Join(workspace.Directory, "variables.tf")))
	if !strings.Contains(backend, `region       = "eu-west-1"`) ||
		!strings.Contains(backend, `use_lockfile = true`) ||
		!strings.Contains(backend, resource.ID.String()) || !strings.Contains(variables, `"us-east-1"`) {
		t.Fatal("backend region, lock, state key or provider region is incorrect")
	}
}

func TestVPCGeneratorValidatesAWSIPv4Prefix(t *testing.T) {
	generator := NewGenerator(t.TempDir(), "")
	resource := testResource()
	resource.ResourceType = "aws_vpc"
	for _, tc := range []struct {
		cidr  string
		valid bool
	}{
		{"10.0.0.0/15", false},
		{"10.0.0.0/16", true},
		{"10.0.0.0/28", true},
		{"10.0.0.0/29", false},
		{"::ffff:10.0.0.0/112", false},
	} {
		resource.Configuration = map[string]any{"cidr_block": tc.cidr}
		if _, err := generator.Generate(resource); (err == nil) != tc.valid {
			t.Errorf("generate VPC for %s: %v", tc.cidr, err)
		}
	}
}

func TestProvisionerRoleIsolatedFromStateBackend(t *testing.T) {
	generator := NewGenerator(t.TempDir(), "test-state")
	const role = "arn:aws:iam::123456789012:role/cloudforge-terraform-provisioner"
	generator.ProvisionerRoleARN = role
	resource := testResource()
	if !strings.Contains(generator.versionsFile(), "assume_role {") ||
		!strings.Contains(generator.versionsFile(), `role_arn = "`+role+`"`) ||
		strings.Contains(generator.backendFile(resource), role) {
		t.Fatal("provider role must be separate from the backend identity")
	}
	runner := NewRunner(generator)
	binding := runner.remotePlanBinding(resource, "approved-plan")
	generator.ProvisionerRoleARN = ""
	if binding == runner.remotePlanBinding(resource, "approved-plan") {
		t.Fatal("removing the role must invalidate an existing plan binding")
	}
}

func TestAWSSubnetInputsRejectInvalidOrDuplicateIDs(t *testing.T) {
	for _, tc := range []struct {
		resourceType string
		subnets      []string
	}{
		{"aws_rds", []string{"subnet-11111111"}},
		{"aws_eks", []string{"subnet-11111111", "subnet-11111111"}},
		{"aws_eks", []string{"subnet-11111111", "placeholder"}},
	} {
		resource := testResource()
		resource.ResourceType = tc.resourceType
		resource.Configuration = map[string]any{"subnet_ids": tc.subnets}
		if _, err := NewGenerator(t.TempDir(), "").Generate(resource); err == nil {
			t.Errorf("%s accepted invalid subnet inputs", tc.resourceType)
		}
	}
}

func TestRoleBoundResourcesUseReservedNamesAndTags(t *testing.T) {
	g := NewGenerator(t.TempDir(), "")
	g.ProvisionerRoleARN = "arn:aws:iam::123456789012:role/cloudforge-terraform-provisioner"
	resource := testResource()
	resource.Configuration = map[string]any{
		"tags":       map[string]any{"cloudforge": "false", "owner": "app"},
		"subnet_ids": []string{"subnet-11111111", "subnet-22222222"},
	}
	for _, kind := range []string{"aws_rds", "aws_eks"} {
		resource.ResourceType = kind
		ws, err := g.Generate(resource)
		if err != nil {
			t.Fatal(err)
		}
		hcl := string(mustReadFile(t, filepath.Join(ws.Directory, "main.tf")))
		if strings.Contains(hcl, "\"cloudforge\" = \"false\"") ||
			!strings.Contains(hcl, `"cloudforge-`+resource.ID.String()+`"`) {
			t.Fatalf("%s escaped the scoped role namespace or overrode the ownership tag", kind)
		}
	}
}

func TestEC2PublicAMIIsResolvedDuringPlan(t *testing.T) {
	r := testResource()
	r.ResourceType = "aws_ec2"
	r.Configuration = map[string]any{
		"instance_type": "t3.micro", "subnet_id": "subnet-11111111",
		"ami_id": "resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64",
	}
	hcl, err := NewGenerator(t.TempDir(), "").ec2File(r)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(hcl, `data "aws_ssm_parameter" "ami"`) ||
		!strings.Contains(hcl, "with_decryption = false") ||
		!strings.Contains(hcl, "ami                         = data.aws_ssm_parameter.ami.value") ||
		strings.Contains(hcl, "resolve:ssm:") {
		t.Fatal("AMI alias was not resolved as plan-time data")
	}
}
