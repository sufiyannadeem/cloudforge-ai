package config

import (
	"testing"
)

func TestConfigDevelopmentDefaults(t *testing.T) {
	t.Setenv("APP_ENV", "development")
	t.Setenv("DATABASE_URL", "")
	t.Setenv("SERVER_PORT", "8080")
	t.Setenv("SHUTDOWN_TIMEOUT_SECONDS", "10")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("expected development config to load successfully, got: %v", err)
	}

	if cfg.DatabaseURL == "" {
		t.Fatal("expected default database URL in development mode")
	}
}

func TestConfigProductionRequiresExplicitDatabaseURL(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	t.Setenv("DATABASE_URL", "")

	_, err := Load()
	if err == nil {
		t.Fatal("expected production config to fail when DATABASE_URL is empty")
	}
}

func TestConfigProductionRejectsLocalhostDatabaseURL(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	t.Setenv("DATABASE_URL", "postgres://user:pass@localhost:5432/cloudforge")

	_, err := Load()
	if err == nil {
		t.Fatal("expected production config to reject localhost DATABASE_URL")
	}
}

func TestConfigProductionRejectsPlaceholderDatabaseURL(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	t.Setenv("DATABASE_URL", "postgres://user:replace-with-a-password@db.prod.internal:5432/cloudforge")

	_, err := Load()
	if err == nil {
		t.Fatal("expected production config to reject placeholder DATABASE_URL")
	}
}

func TestConfigProductionAcceptsValidDatabaseURL(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	t.Setenv("DATABASE_URL", "postgres://cloudforge:realprodsecret@db-cluster.internal:5432/cloudforge")
	t.Setenv("SERVER_PORT", "8080")
	t.Setenv("SHUTDOWN_TIMEOUT_SECONDS", "15")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("expected valid production config to succeed, got: %v", err)
	}

	if cfg.AppEnv != "production" {
		t.Fatalf("expected production environment, got %s", cfg.AppEnv)
	}
}

func TestConfigRejectsInvalidPort(t *testing.T) {
	t.Setenv("SERVER_PORT", "99999")

	_, err := Load()
	if err == nil {
		t.Fatal("expected error for invalid port")
	}
}
