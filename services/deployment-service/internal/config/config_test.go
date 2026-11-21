package config

import (
	"os"
	"testing"
)

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

func TestConfigValidateProductionRequiresKubernetesConfig(t *testing.T) {
	cfg := Config{
		AppEnv:                 "production",
		ServerPort:             8082,
		DatabaseURL:            "postgres://cloudforge:realprodpassword@db.prod.internal:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
		RolloutTimeoutSeconds:  120,
		// No KubeConfig, EKSClusterName, or in-cluster credentials
	}

	// Ensure environment has no KUBECONFIG
	t.Setenv("KUBECONFIG", "")
	t.Setenv("KUBERNETES_SERVICE_HOST", "")

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error for missing Kubernetes configuration in production")
	}
}

func TestConfigValidateProductionRejectsLocalhostDatabaseURL(t *testing.T) {
	cfg := Config{
		AppEnv:                 "production",
		ServerPort:             8082,
		DatabaseURL:            "postgres://localhost:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
		RolloutTimeoutSeconds:  120,
		EKSClusterName:         "test-cluster",
	}

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error for localhost database URL in production")
	}
}

func TestConfigValidateProductionRejectsSimulatedExecutor(t *testing.T) {
	cfg := Config{
		AppEnv:                 "production",
		ServerPort:             8082,
		DatabaseURL:            "postgres://localhost:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
		RolloutTimeoutSeconds:  120,
		DeploymentExecutor:     "simulated",
		EKSClusterName:         "cloudforge-prod-cluster",
	}

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error when simulated executor is configured in production")
	}
}

func TestConfigValidateProductionWithEKSClusterSuccess(t *testing.T) {
	cfg := Config{
		AppEnv:                 "production",
		ServerPort:             8082,
		DatabaseURL:            "postgres://cloudforge:realprodpassword@db.prod.internal:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
		RolloutTimeoutSeconds:  120,
		DeploymentExecutor:     "kubernetes",
		EKSClusterName:         "cloudforge-dev-eks",
		AWSRegion:              "eu-west-1",
		KubernetesNamespace:    "default",
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected valid production config with EKS cluster, got: %v", err)
	}
}

func TestConfigValidateProductionWithKubeConfigSuccess(t *testing.T) {
	tmpFile, err := os.CreateTemp("", "kubeconfig-*")
	if err != nil {
		t.Fatalf("failed to create temp kubeconfig: %v", err)
	}
	defer os.Remove(tmpFile.Name())
	tmpFile.Close()

	cfg := Config{
		AppEnv:                 "production",
		ServerPort:             8082,
		DatabaseURL:            "postgres://cloudforge:realprodpassword@db.prod.internal:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
		RolloutTimeoutSeconds:  120,
		KubeConfig:             tmpFile.Name(),
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected valid production config with KubeConfig, got: %v", err)
	}
}

func TestConfigValidateProductionWithMissingKubeConfigFails(t *testing.T) {
	cfg := Config{
		AppEnv:                 "production",
		ServerPort:             8082,
		DatabaseURL:            "postgres://cloudforge:realprodpassword@db.prod.internal:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
		RolloutTimeoutSeconds:  120,
		KubeConfig:             "/non/existent/path/kubeconfig",
	}

	t.Setenv("KUBERNETES_SERVICE_HOST", "")

	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error for non-existent KubeConfig in production")
	}
}

func TestConfigValidateDevelopmentAllowsSimulated(t *testing.T) {
	cfg := Config{
		AppEnv:                 "development",
		ServerPort:             8082,
		DatabaseURL:            "postgres://localhost:5432/cloudforge",
		ShutdownTimeoutSeconds: 10,
		RolloutTimeoutSeconds:  120,
		DeploymentExecutor:     "simulated",
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected valid development config with simulated executor, got: %v", err)
	}
}

func TestMigrationDoesNotRelaxRuntimeKubernetesRequirement(t *testing.T) {
	t.Setenv("KUBERNETES_SERVICE_HOST", "")
	cfg := Config{AppEnv: "production", ServerPort: 8082, DatabaseURL: "postgres://cf_migrator@database/cloudforge?sslmode=verify-full", ShutdownTimeoutSeconds: 10}
	if err := cfg.Validate(true); err != nil {
		t.Fatal(err)
	}
	if err := cfg.Validate(); err == nil {
		t.Fatal("runtime accepted missing Kubernetes ownership/configuration")
	}
}
