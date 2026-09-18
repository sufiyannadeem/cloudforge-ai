package config

import "testing"

func TestConfigValidateSuccess(t *testing.T) {
	cfg := Config{
		AppEnv:                 "development",
		ServerPort:             8082,
		DatabaseURL:            "postgres://localhost:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected valid config, got error: %v", err)
	}
}

func TestConfigValidateRejectsEmptyDatabaseURL(t *testing.T) {
	cfg := Config{
		AppEnv:                 "development",
		ServerPort:             8082,
		DatabaseURL:            "",
		ShutdownTimeoutSeconds: 10,
	}

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error for empty database URL")
	}
}

func TestConfigValidateRejectsInvalidPort(t *testing.T) {
	cfg := Config{
		AppEnv:                 "development",
		ServerPort:             70000,
		DatabaseURL:            "postgres://localhost:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
	}

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error for invalid port")
	}
}
