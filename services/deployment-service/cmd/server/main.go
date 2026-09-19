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

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/config"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/database"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/handler"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/metrics"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/worker"
)

func main() {
	logger := slog.New(
		slog.NewJSONHandler(
			os.Stdout,
			&slog.HandlerOptions{
				Level: slog.LevelInfo,
			},
		),
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

	attemptRepository, err := repository.NewDeploymentAttemptRepository(pool)
	if err != nil {
		logger.Error(
			"failed to create deployment attempt repository",
			"error",
			err,
		)
		os.Exit(1)
	}

	deploymentService := service.NewDeploymentService(
		deploymentRepository,
	)

	metricsRegistry := prometheus.NewRegistry()

	serviceMetrics := metrics.New()

	if err := serviceMetrics.Register(
		metricsRegistry,
	); err != nil {
		logger.Error(
			"failed to register HTTP metrics",
			"error",
			err,
		)
		os.Exit(1)
	}

	deploymentMetrics := metrics.NewDeploymentMetrics()

	if err := deploymentMetrics.Register(
		metricsRegistry,
	); err != nil {
		logger.Error(
			"failed to register deployment metrics",
			"error",
			err,
		)
		os.Exit(1)
	}

	metricsHandler := promhttp.HandlerFor(
		metricsRegistry,
		promhttp.HandlerOpts{},
	)

	simulatedExecutor := executor.SimulatedExecutor{
		ExecutionDelay: 2 * time.Second,
		ShouldFail:     false,
	}

	deploymentRunner, err := service.NewDeploymentRunnerWithAttemptsAndMetrics(
		deploymentService,
		attemptRepository,
		simulatedExecutor,
		logger,
		deploymentMetrics,
	)
	if err != nil {
		logger.Error(
			"failed to create deployment runner",
			"error",
			err,
		)
		os.Exit(1)
	}

	deploymentWorker, err := worker.New(
		worker.Config{
			QueueSize: 100,
			Workers:   2,
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
		},
	)
	if err != nil {
		logger.Error(
			"failed to create deployment worker",
			"error",
			err,
		)
		os.Exit(1)
	}

	deploymentWorker.Start()

	deploymentHandler := handler.NewDeploymentHandler(
		deploymentService,
	)

	queuedDeploymentHandler := handler.NewQueuedDeploymentHandler(
		deploymentService,
		deploymentWorker,
	)

	deploymentAttemptHandler := handler.NewDeploymentAttemptHandler(
		deploymentService,
		attemptRepository,
	)

	router := handler.NewRouterWithDependenciesAndMetrics(
		deploymentHandler,
		queuedDeploymentHandler,
		deploymentAttemptHandler,
		metricsHandler,
	)

	instrumentedRouter := metrics.Middleware(
		serviceMetrics,
	)(router)

	server := &http.Server{
		Addr: ":" + strconv.Itoa(cfg.ServerPort),

		Handler: instrumentedRouter,

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
			"prometheus_metrics",
			true,
			"worker_count",
			2,
			"queue_size",
			100,
		)

		serverErrors <- server.ListenAndServe()
	}()

	select {
	case err := <-serverErrors:
		if !errors.Is(
			err,
			http.ErrServerClosed,
		) {
			logger.Error(
				"HTTP server failed",
				"error",
				err,
			)

			deploymentWorker.Shutdown()

			os.Exit(1)
		}

	case <-shutdownContext.Done():
		logger.Info(
			"shutdown signal received",
		)
	}

	shutdownTimeout := time.Duration(
		cfg.ShutdownTimeoutSeconds,
	) * time.Second

	shutdownCtx, cancel := context.WithTimeout(
		context.Background(),
		shutdownTimeout,
	)
	defer cancel()

	if err := server.Shutdown(
		shutdownCtx,
	); err != nil {
		logger.Error(
			"graceful HTTP server shutdown failed",
			"error",
			err,
		)

		deploymentWorker.Shutdown()

		os.Exit(1)
	}

	deploymentWorker.Shutdown()

	logger.Info(
		"deployment service stopped successfully",
	)
}
