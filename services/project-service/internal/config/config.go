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

	return Config{
		AppEnv:                 getEnv("APP_ENV", "development"),
		ServerPort:             serverPort,
		DatabaseURL:            getEnv("DATABASE_URL", "postgres://cloudforge:cloudforge_password@localhost:5432/cloudforge?sslmode=disable"),
		ShutdownTimeoutSeconds: timeout,
	}, nil
}

func getEnv(key string, fallback string) string {
	value := os.Getenv(key)

	if value == "" {
		return fallback
	}

	return value
}
