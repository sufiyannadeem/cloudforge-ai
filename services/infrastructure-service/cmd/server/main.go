package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/config"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/database"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/handler"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"

	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func main() {
	logger := log.New(
		os.Stdout,
		"infrastructure-service: ",
		log.LstdFlags,
	)

	cfg, err := config.Load()
	if err != nil {
		logger.Fatalf("load configuration: %v", err)
	}

	frontendKey := os.Getenv("CLOUDFORGE_FRONTEND_KEY")

	ctx := context.Background()

	pool, err := database.NewPool(ctx, database.Config{
		DatabaseURL: cfg.DatabaseURL,
	})
	if err != nil {
		logger.Fatalf("initialize database: %v", err)
	}
	defer pool.Close()

	migrationRunner := migration.NewRunner(pool)

	if err := migrationRunner.Run(ctx); err != nil {
		logger.Fatalf("run database migrations: %v", err)
	}

	resourceRepository := repository.NewResourceRepository(pool)

	resourceService := service.NewResourceService(
		resourceRepository,
	)

	workspaceRoot := getEnv(
		"TERRAFORM_WORKSPACE_ROOT",
		"/var/lib/cloudforge/terraform",
	)

	terraformBinary := getEnv(
		"TERRAFORM_BINARY",
		"terraform",
	)

	planTimeout := getDurationEnv(
		"TERRAFORM_PLAN_TIMEOUT",
		10*time.Minute,
	)

	applyTimeout := getDurationEnv(
		"TERRAFORM_APPLY_TIMEOUT",
		30*time.Minute,
	)

	terraformGenerator := terraform.NewGenerator(
		workspaceRoot,
		cfg.TerraformStateBucket,
	)
	terraformGenerator.StateRegion = cfg.TerraformStateRegion
	terraformGenerator.ProvisionerRoleARN = strings.TrimSpace(os.Getenv("TERRAFORM_PROVISIONER_ROLE_ARN"))

	terraformRunner := terraform.NewRunner(
		terraformGenerator,
	)
	terraformRunner.RequireRemoteState = cfg.AppEnv == "production"

	terraformRunner.TerraformBin = terraformBinary
	terraformRunner.PlanTimeout = planTimeout
	terraformRunner.ApplyTimeout = applyTimeout

	provisioningService := service.NewProvisioningService(
		resourceRepository,
		terraformRunner,
	)

	resourceHandler := handler.NewResourceHandler(
		resourceService,
		provisioningService,
	)

	resourceHandler.TerraformReadOnly = cfg.TerraformReadOnly
	resourceHandler.DriftStore = resourceRepository
	resourceHandler.DriftRunner = terraformRunner

	router := handler.NewAuthenticatedRouter(resourceHandler, frontendKey, func(ctx context.Context, claims identity.Claims) error {
		consumed, err := resourceRepository.ConsumeApprovalAssertion(ctx, claims.Nonce, claims.Expiry)
		if err == nil && !consumed {
			return identity.ErrReplay
		}
		return err
	}, identity.ProjectAccess{DB: pool})

	server := &http.Server{
		Addr:              ":" + cfg.ServerPort,
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       applyTimeout + 5*time.Minute,
		WriteTimeout:      applyTimeout + 5*time.Minute,
		IdleTimeout:       60 * time.Second,
	}

	serverErrors := make(chan error, 1)

	go func() {
		logger.Printf(
			"server listening on port %s",
			cfg.ServerPort,
		)

		if err := server.ListenAndServe(); err != nil &&
			!errors.Is(err, http.ErrServerClosed) {
			serverErrors <- err
		}
	}()

	signalContext, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	select {
	case err := <-serverErrors:
		logger.Fatalf("server error: %v", err)

	case <-signalContext.Done():
		logger.Println("shutdown signal received")
	}

	shutdownContext, cancel := context.WithTimeout(
		context.Background(),
		time.Duration(cfg.ShutdownTimeoutSeconds)*time.Second,
	)
	defer cancel()

	if err := server.Shutdown(shutdownContext); err != nil {
		logger.Printf(
			"graceful shutdown failed: %v",
			err,
		)

		if closeErr := server.Close(); closeErr != nil {
			logger.Printf(
				"force server close failed: %v",
				closeErr,
			)
		}
	}

	logger.Println("server stopped")
}

func getEnv(key string, fallback string) string {
	value := os.Getenv(key)

	if value == "" {
		return fallback
	}

	return value
}

func getDurationEnv(
	key string,
	fallback time.Duration,
) time.Duration {
	value := os.Getenv(key)

	if value == "" {
		return fallback
	}

	duration, err := time.ParseDuration(value)
	if err != nil {
		return fallback
	}

	return duration
}
