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
		ResourceType: "aws_rds",
	}

	_, err := generator.Generate(resource)

	if err == nil {
		t.Fatal("expected unsupported resource type error")
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
