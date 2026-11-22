package config

import (
	"os"
	"strings"
	"testing"

	identity "github.com/sufiyannadeem/cloudforge-service-identity"
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

func TestInfrastructureServiceStartupDatabaseValidationDevelopment(t *testing.T) {
	t.Setenv("APP_ENV", "development")
	t.Setenv("DATABASE_URL", "postgres://cloudforge:secret@postgres:5432/cloudforge?sslmode=disable")
	t.Setenv("SERVER_PORT", "8081")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("expected valid development config, got: %v", err)
	}

	if err := identity.ValidateDatabase(cfg.AppEnv, cfg.DatabaseURL, "infrastructure", false); err != nil {
		t.Fatalf("expected development database validation to succeed, got: %v", err)
	}
}

func TestInfrastructureServiceStartupDatabaseValidationProductionFailClosed(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	// Local Compose settings in production must fail closed
	t.Setenv("DATABASE_URL", "postgres://cloudforge:secret@postgres:5432/cloudforge?sslmode=disable")
	t.Setenv("SERVER_PORT", "8081")
	t.Setenv("TERRAFORM_READ_ONLY", "true")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("expected config.Load to succeed with read-only in production, got: %v", err)
	}

	err = identity.ValidateDatabase(cfg.AppEnv, cfg.DatabaseURL, "infrastructure", false)
	if err == nil {
		t.Fatal("expected production database validation to fail with local Compose credentials, got nil")
	}
	if !strings.Contains(err.Error(), "production requires a dedicated database principal and hostname-verified TLS") {
		t.Fatalf("unexpected error message: %v", err)
	}

	// Dedicated production principal and verify-full TLS succeeds
	prodDSN := "postgres://cf_infrastructure:secret@db.prod.internal:5432/cloudforge?sslmode=verify-full"
	if err := identity.ValidateDatabase(cfg.AppEnv, prodDSN, "infrastructure", false); err != nil {
		t.Fatalf("expected production database validation to succeed for cf_infrastructure verify-full, got: %v", err)
	}
}
