package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	AppEnv                 string
	ServerPort             int
	DatabaseURL            string
	ShutdownTimeoutSeconds int
}

func Load() (Config, error) {
	cfg := Config{
		AppEnv:                 getEnv("APP_ENV", "development"),
		ServerPort:             getEnvInt("SERVER_PORT", 8082),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		ShutdownTimeoutSeconds: getEnvInt("SHUTDOWN_TIMEOUT_SECONDS", 10),
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

	return nil
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
