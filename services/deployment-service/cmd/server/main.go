package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/config"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/database"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/handler"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/worker"
)

const (
	workerCount = 2
	queueSize   = 100
)

func main() {
	logger := slog.New(
		slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
			Level: slog.LevelInfo,
		}),
	)

	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		logger.Error(
			"failed to load configuration",
			"error",
			err,
		)
		os.Exit(1)
	}

	ctx := context.Background()

	pool, err := database.NewPool(
		ctx,
		cfg.DatabaseURL,
	)
	if err != nil {
		logger.Error(
			"failed to connect to database",
			"error",
			err,
		)
		os.Exit(1)
	}
	defer pool.Close()

	migrationRunner := migration.NewRunner(pool)

	if err := migrationRunner.Run(ctx); err != nil {
		logger.Error(
			"failed to run database migrations",
			"error",
			err,
		)
		os.Exit(1)
	}

	deploymentRepository := repository.NewDeploymentRepository(pool)

	deploymentService := service.NewDeploymentService(
		deploymentRepository,
	)

	deploymentExecutor := executor.SimulatedExecutor{
		ExecutionDelay: 2 * time.Second,
		ShouldFail:     false,
	}

	deploymentRunner, err := service.NewDeploymentRunner(
		deploymentService,
		deploymentExecutor,
		logger,
	)
	if err != nil {
		logger.Error(
			"failed to create deployment runner",
			"error",
			err,
		)
		os.Exit(1)
	}

	deploymentWorker, err := worker.New(worker.Config{
		QueueSize: queueSize,
		Workers:   workerCount,
		Handler: func(
			ctx context.Context,
			job worker.Job,
		) error {
			return deploymentRunner.Run(
				ctx,
				job.DeploymentID,
			)
		},
		Logger: logger,
	})
	if err != nil {
		logger.Error(
			"failed to create deployment worker",
			"error",
			err,
		)
		os.Exit(1)
	}

	deploymentWorker.Start()
	defer deploymentWorker.Shutdown()

	deploymentHandler := handler.NewDeploymentHandler(
		deploymentService,
	)

	queuedDeploymentHandler := handler.NewQueuedDeploymentHandler(
		deploymentService,
		deploymentWorker,
	)

	router := handler.NewRouterWithQueue(
		deploymentHandler,
		queuedDeploymentHandler,
	)

	server := &http.Server{
		Addr:              ":" + strconv.Itoa(cfg.ServerPort),
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	shutdownContext, stop := signal.NotifyContext(
		context.Background(),
		syscall.SIGINT,
		syscall.SIGTERM,
	)
	defer stop()

	serverErrors := make(chan error, 1)

	go func() {
		logger.Info(
			"deployment service started",
			"port",
			cfg.ServerPort,
			"environment",
			cfg.AppEnv,
			"worker_count",
			workerCount,
			"queue_size",
			queueSize,
		)

		serverErrors <- server.ListenAndServe()
	}()

	select {
	case err := <-serverErrors:
		if !errors.Is(err, http.ErrServerClosed) {
			logger.Error(
				"HTTP server failed",
				"error",
				err,
			)
			os.Exit(1)
		}

	case <-shutdownContext.Done():
		logger.Info("shutdown signal received")
	}

	shutdownTimeout := time.Duration(
		cfg.ShutdownTimeoutSeconds,
	) * time.Second

	shutdownCtx, cancel := context.WithTimeout(
		context.Background(),
		shutdownTimeout,
	)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.Error(
			"graceful shutdown failed",
			"error",
			err,
		)
		os.Exit(1)
	}

	logger.Info("deployment service stopped successfully")
}
