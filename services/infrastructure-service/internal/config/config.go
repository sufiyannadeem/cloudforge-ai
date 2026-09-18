package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	AppEnv                 string
	ServerPort             string
	DatabaseURL            string
	ShutdownTimeoutSeconds int
}

func Load() (Config, error) {
	config := Config{
		AppEnv:                 getEnv("APP_ENV", "development"),
		ServerPort:             getEnv("SERVER_PORT", "8081"),
		DatabaseURL:            getEnv("DATABASE_URL", ""),
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
