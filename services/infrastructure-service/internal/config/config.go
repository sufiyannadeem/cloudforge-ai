package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	AppEnv                 string
	ServerPort             string
	DatabaseURL            string
	TerraformReadOnly      bool
	TerraformStateBucket   string
	TerraformStateRegion   string
	ShutdownTimeoutSeconds int
}

func Load() (Config, error) {
	readOnly, err := strconv.ParseBool(getEnv("TERRAFORM_READ_ONLY", "false"))
	if err != nil {
		return Config{}, fmt.Errorf("TERRAFORM_READ_ONLY must be a boolean")
	}
	config := Config{
		TerraformReadOnly:      readOnly,
		AppEnv:                 getEnv("APP_ENV", "development"),
		ServerPort:             getEnv("SERVER_PORT", "8081"),
		DatabaseURL:            getEnv("DATABASE_URL", ""),
		TerraformStateBucket:   strings.TrimSpace(os.Getenv("TERRAFORM_STATE_BUCKET")),
		TerraformStateRegion:   strings.TrimSpace(getEnv("TERRAFORM_STATE_REGION", getEnv("AWS_REGION", getEnv("AWS_DEFAULT_REGION", "")))),
		ShutdownTimeoutSeconds: getIntEnv("SHUTDOWN_TIMEOUT_SECONDS", 10),
	}

	if err := config.Validate(); err != nil {
		return Config{}, err
	}

	return config, nil
}

func (c Config) Validate() error {
	if c.AppEnv == "" {
		return fmt.Errorf("APP_ENV cannot be empty")
	}

	if c.ServerPort == "" {
		return fmt.Errorf("SERVER_PORT cannot be empty")
	}

	port, err := strconv.Atoi(c.ServerPort)
	if err != nil || port < 1 || port > 65535 {
		return fmt.Errorf("SERVER_PORT must be a valid port between 1 and 65535")
	}

	if c.DatabaseURL == "" {
		return fmt.Errorf("DATABASE_URL cannot be empty")
	}

	if c.AppEnv == "production" {
		lowerURL := strings.ToLower(c.DatabaseURL)
		if strings.Contains(lowerURL, "localhost") || strings.Contains(lowerURL, "replace-with") {
			return fmt.Errorf("production environment must not use default localhost or placeholder DATABASE_URL")
		}
		if !c.TerraformReadOnly && strings.TrimSpace(c.TerraformStateBucket) == "" {
			return fmt.Errorf("production requires TERRAFORM_STATE_BUCKET for locked remote Terraform state")
		}
		if !c.TerraformReadOnly && strings.TrimSpace(c.TerraformStateRegion) == "" {
			return fmt.Errorf("production requires TERRAFORM_STATE_REGION or an AWS region for the remote state bucket")
		}
	}

	if c.ShutdownTimeoutSeconds <= 0 {
		return fmt.Errorf("SHUTDOWN_TIMEOUT_SECONDS must be greater than zero")
	}

	return nil
}

func getEnv(key string, defaultValue string) string {
	value, exists := os.LookupEnv(key)

	if !exists || value == "" {
		return defaultValue
	}

	return value
}

func getIntEnv(key string, defaultValue int) int {
	value := os.Getenv(key)

	if value == "" {
		return defaultValue
	}

	parsedValue, err := strconv.Atoi(value)

	if err != nil {
		return defaultValue
	}

	return parsedValue
}
