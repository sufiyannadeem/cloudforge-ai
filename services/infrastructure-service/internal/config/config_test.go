package config

import (
	"os"
	"testing"
)

func TestConfigValidateSuccess(t *testing.T) {
	config := Config{
		AppEnv:                 "development",
		ServerPort:             "8081",
		DatabaseURL:            "postgres://user:password@localhost:5432/database",
		ShutdownTimeoutSeconds: 10,
	}

	if err := config.Validate(); err != nil {
		t.Fatalf("expected valid configuration, got error: %v", err)
	}
}

func TestConfigValidateInvalidPort(t *testing.T) {
	config := Config{
		AppEnv:                 "development",
		ServerPort:             "99999",
		DatabaseURL:            "postgres://user:password@localhost:5432/database",
		ShutdownTimeoutSeconds: 10,
	}

	if err := config.Validate(); err == nil {
		t.Fatal("expected invalid port error, got nil")
	}
}

func TestConfigValidateMissingDatabaseURL(t *testing.T) {
	config := Config{
		AppEnv:                 "development",
		ServerPort:             "8081",
		DatabaseURL:            "",
		ShutdownTimeoutSeconds: 10,
	}

	if err := config.Validate(); err == nil {
		t.Fatal("expected database URL error, got nil")
	}
}

func TestConfigValidateInvalidShutdownTimeout(t *testing.T) {
	config := Config{
		AppEnv:                 "development",
		ServerPort:             "8081",
		DatabaseURL:            "postgres://user:password@localhost:5432/database",
		ShutdownTimeoutSeconds: 0,
	}

	if err := config.Validate(); err == nil {
		t.Fatal("expected shutdown timeout error, got nil")
	}
}

func TestGetEnvUsesDefaultValue(t *testing.T) {
	const key = "CLOUDFORGE_TEST_ENV"

	os.Unsetenv(key)
	defer os.Unsetenv(key)

	result := getEnv(key, "default-value")

	if result != "default-value" {
		t.Fatalf("expected default-value, got %s", result)
	}
}

func TestGetEnvUsesEnvironmentValue(t *testing.T) {
	const key = "CLOUDFORGE_TEST_ENV"

	os.Setenv(key, "custom-value")
	defer os.Unsetenv(key)

	result := getEnv(key, "default-value")

	if result != "custom-value" {
		t.Fatalf("expected custom-value, got %s", result)
	}
}

func TestGetIntEnvUsesDefaultForInvalidValue(t *testing.T) {
	const key = "CLOUDFORGE_TEST_INT"

	os.Setenv(key, "invalid-number")
	defer os.Unsetenv(key)

	result := getIntEnv(key, 10)

	if result != 10 {
		t.Fatalf("expected default value 10, got %d", result)
	}
}

func TestConfigValidateProductionRejectsLocalhostDatabaseURL(t *testing.T) {
	config := Config{
		AppEnv:                 "production",
		ServerPort:             "8081",
		DatabaseURL:            "postgres://cloudforge:pass@localhost:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
	}

	if err := config.Validate(); err == nil {
		t.Fatal("expected error for localhost database URL in production")
	}
}

func TestConfigValidateProductionAcceptsValidDatabaseURL(t *testing.T) {
	config := Config{
		AppEnv:                 "production",
		TerraformStateBucket:   "test-state-bucket",
		TerraformStateRegion:   "eu-west-1",
		ServerPort:             "8081",
		DatabaseURL:            "postgres://cloudforge:realprodpassword@db.prod.internal:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
	}

	if err := config.Validate(); err != nil {
		t.Fatalf("expected valid production config to succeed, got: %v", err)
	}
}

func TestProductionRequiresRemoteTerraformState(t *testing.T) {
	config := Config{AppEnv: "production", ServerPort: "8081", DatabaseURL: "postgres://db.internal/database", ShutdownTimeoutSeconds: 10}
	if err := config.Validate(); err == nil {
		t.Fatal("production started without durable Terraform state")
	}
}

func TestExplicitReadOnlyProductionCanServeInventoryWithoutBackend(t *testing.T) {
	config := Config{AppEnv: "production", ServerPort: "8081", DatabaseURL: "postgres://db.internal/database",
		ShutdownTimeoutSeconds: 10, TerraformReadOnly: true}
	if err := config.Validate(); err != nil {
		t.Fatalf("read-only inventory unavailable: %v", err)
	}
	config.TerraformReadOnly = false
	if err := config.Validate(); err == nil {
		t.Fatal("execution enabled without durable state")
	}
}

func TestReadOnlyModeRejectsMalformedFlag(t *testing.T) {
	t.Setenv("TERRAFORM_READ_ONLY", "not-a-boolean")
	if _, err := Load(); err == nil {
		t.Fatal("invalid read-only configuration accepted")
	}
}
