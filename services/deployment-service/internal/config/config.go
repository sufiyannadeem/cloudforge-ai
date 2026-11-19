package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	AppEnv                 string
	ServerPort             int
	DatabaseURL            string
	ShutdownTimeoutSeconds int

	// Kubernetes / EKS deployment configuration
	DeploymentExecutor    string
	KubeConfig            string
	EKSClusterName        string
	AWSRegion             string
	KubernetesNamespace   string
	KubectlPath           string
	AWSCLIPath            string
	RolloutTimeoutSeconds int
}

func Load() (Config, error) {
	cfg := Config{
		AppEnv:                 getEnv("APP_ENV", "development"),
		ServerPort:             getEnvInt("SERVER_PORT", 8082),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		ShutdownTimeoutSeconds: getEnvInt("SHUTDOWN_TIMEOUT_SECONDS", 10),

		DeploymentExecutor:    getEnv("DEPLOYMENT_EXECUTOR", ""),
		KubeConfig:            getEnv("KUBECONFIG", ""),
		EKSClusterName:        getEnv("EKS_CLUSTER_NAME", getEnv("KUBERNETES_CLUSTER_NAME", "")),
		AWSRegion:             getEnv("AWS_REGION", getEnv("AWS_DEFAULT_REGION", "eu-west-1")),
		KubernetesNamespace:   getEnv("KUBERNETES_NAMESPACE", "default"),
		KubectlPath:           getEnv("KUBECTL_PATH", "kubectl"),
		AWSCLIPath:            getEnv("AWS_CLI_PATH", "aws"),
		RolloutTimeoutSeconds: getEnvInt("ROLLOUT_TIMEOUT_SECONDS", 120),
	}

	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}

	return cfg, nil
}

func (c Config) Validate() error {
	if c.AppEnv == "" {
		return fmt.Errorf("APP_ENV cannot be empty")
	}

	if c.ServerPort < 1 || c.ServerPort > 65535 {
		return fmt.Errorf("SERVER_PORT must be between 1 and 65535")
	}

	if c.DatabaseURL == "" {
		return fmt.Errorf("DATABASE_URL cannot be empty")
	}

	if c.ShutdownTimeoutSeconds <= 0 {
		return fmt.Errorf("SHUTDOWN_TIMEOUT_SECONDS must be greater than zero")
	}

	if c.RolloutTimeoutSeconds < 0 {
		return fmt.Errorf("ROLLOUT_TIMEOUT_SECONDS cannot be negative")
	}

	if c.DeploymentExecutor != "" && c.DeploymentExecutor != "kubernetes" && c.DeploymentExecutor != "simulated" {
		return fmt.Errorf("invalid DEPLOYMENT_EXECUTOR %q: must be 'kubernetes' or 'simulated'", c.DeploymentExecutor)
	}

	if c.AppEnv == "production" {
		lowerURL := strings.ToLower(c.DatabaseURL)
		if strings.Contains(lowerURL, "localhost") || strings.Contains(lowerURL, "replace-with") {
			return fmt.Errorf("production environment must not use default localhost or placeholder DATABASE_URL")
		}

		if c.DeploymentExecutor == "simulated" {
			return fmt.Errorf("simulated deployment executor is not permitted in production environment")
		}

		if !c.HasKubernetesConfig() {
			return fmt.Errorf("incomplete production Kubernetes configuration: KUBECONFIG, in-cluster credentials, or EKS_CLUSTER_NAME must be configured")
		}
	}

	return nil
}

// HasKubernetesConfig checks whether sufficient configuration exists to connect to a real Kubernetes or EKS cluster.
func (c Config) HasKubernetesConfig() bool {
	// 1. In-cluster Kubernetes environment
	if os.Getenv("KUBERNETES_SERVICE_HOST") != "" {
		return true
	}
	if _, err := os.Stat("/var/run/secrets/kubernetes.io/serviceaccount/token"); err == nil {
		return true
	}

	// 2. Configured EKS cluster name (triggers aws eks update-kubeconfig)
	if strings.TrimSpace(c.EKSClusterName) != "" {
		return true
	}

	// 3. Existing KUBECONFIG file
	if strings.TrimSpace(c.KubeConfig) != "" {
		if _, err := os.Stat(c.KubeConfig); err == nil {
			return true
		}
	}

	return false
}

func getEnv(key, fallback string) string {
	value := os.Getenv(key)

	if value == "" {
		return fallback
	}

	return value
}

func getEnvInt(key string, fallback int) int {
	value := os.Getenv(key)

	if value == "" {
		return fallback
	}

	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}

	return parsed
}
