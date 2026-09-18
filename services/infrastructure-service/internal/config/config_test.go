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
