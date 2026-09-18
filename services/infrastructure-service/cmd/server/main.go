package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/config"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/database"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/handler"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/service"
)

func main() {
	logger := log.New(os.Stdout, "infrastructure-service: ", log.LstdFlags)

	cfg, err := config.Load()
	if err != nil {
		logger.Fatalf("load configuration: %v", err)
	}

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
	resourceService := service.NewResourceService(resourceRepository)
	resourceHandler := handler.NewResourceHandler(resourceService)
	router := handler.NewRouter(resourceHandler)

	server := &http.Server{
		Addr:              ":" + cfg.ServerPort,
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	serverErrors := make(chan error, 1)

	go func() {
		logger.Printf("server listening on port %s", cfg.ServerPort)

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
		logger.Printf("graceful shutdown failed: %v", err)

		if closeErr := server.Close(); closeErr != nil {
			logger.Printf("force server close failed: %v", closeErr)
		}
	}

	logger.Println("server stopped")
}
