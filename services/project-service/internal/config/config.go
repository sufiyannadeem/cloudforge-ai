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
	ShutdownTimeoutSeconds int
}

func Load() (Config, error) {
	serverPort := getEnv("SERVER_PORT", "8080")
	shutdownTimeout := getEnv("SHUTDOWN_TIMEOUT_SECONDS", "10")

	port, err := strconv.Atoi(serverPort)
	if err != nil || port < 1 || port > 65535 {
		return Config{}, fmt.Errorf("invalid SERVER_PORT: %s", serverPort)
	}

	timeout, err := strconv.Atoi(shutdownTimeout)
	if err != nil || timeout < 1 {
		return Config{}, fmt.Errorf(
			"invalid SHUTDOWN_TIMEOUT_SECONDS: %s",
			shutdownTimeout,
		)
	}

	appEnv := getEnv("APP_ENV", "development")
	defaultDBURL := ""
	if appEnv != "production" {
		defaultDBURL = "postgres://cloudforge@localhost:5432/cloudforge?sslmode=disable"
	}

	cfg := Config{
		AppEnv:                 appEnv,
		ServerPort:             serverPort,
		DatabaseURL:            getEnv("DATABASE_URL", defaultDBURL),
		ShutdownTimeoutSeconds: timeout,
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

	if c.ServerPort == "" {
		return fmt.Errorf("SERVER_PORT cannot be empty")
	}

	port, err := strconv.Atoi(c.ServerPort)
	if err != nil || port < 1 || port > 65535 {
		return fmt.Errorf("SERVER_PORT must be a valid port between 1 and 65535")
	}

	if c.ShutdownTimeoutSeconds <= 0 {
		return fmt.Errorf("SHUTDOWN_TIMEOUT_SECONDS must be greater than zero")
	}

	if c.DatabaseURL == "" {
		return fmt.Errorf("DATABASE_URL cannot be empty")
	}

	if c.AppEnv == "production" {
		lowerURL := strings.ToLower(c.DatabaseURL)
		if strings.Contains(lowerURL, "localhost") || strings.Contains(lowerURL, "replace-with") {
			return fmt.Errorf("production environment must not use default localhost or placeholder DATABASE_URL")
		}
	}

	return nil
}

func getEnv(key string, fallback string) string {
	value := os.Getenv(key)

	if value == "" {
		return fallback
	}

	return value
}
