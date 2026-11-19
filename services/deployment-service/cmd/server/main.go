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
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
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

	var deploymentExec executor.Executor
	telemetryHandler := handler.NewProjectTelemetryHandler(nil, "", deploymentRepository)
	if cfg.AppEnv == "production" || cfg.DeploymentExecutor == "kubernetes" {
		k8sOpts := executor.KubernetesOptions{
			ClusterName:      cfg.EKSClusterName,
			AWSRegion:        cfg.AWSRegion,
			DefaultNamespace: cfg.KubernetesNamespace,
			KubectlPath:      cfg.KubectlPath,
			AWSCLIPath:       cfg.AWSCLIPath,
			KubeConfig:       cfg.KubeConfig,
			Timeout:          time.Duration(cfg.RolloutTimeoutSeconds) * time.Second,
		}

		k8sExec, err := executor.NewProductionKubernetesExecutor(deploymentService, k8sOpts)
		if err != nil {
			logger.Error(
				"failed to configure production Kubernetes executor",
				"error",
				err,
			)
			os.Exit(1)
		}

		if err := k8sExec.EnsureClusterConfig(ctx); err != nil {
			logger.Error(
				"failed to authenticate or configure Kubernetes cluster",
				"error",
				err,
				"cluster",
				cfg.EKSClusterName,
				"region",
				cfg.AWSRegion,
			)
			os.Exit(1)
		}

		if err := k8sExec.CheckAPIConnectivity(ctx); err != nil {
			logger.Error(
				"failed to connect to Kubernetes cluster API",
				"error",
				err,
				"cluster",
				cfg.EKSClusterName,
				"region",
				cfg.AWSRegion,
			)
			os.Exit(1)
		}

		deploymentExec = k8sExec
		deploymentRepository.SetExecutionMode("kubernetes")
		telemetryHandler = handler.NewProjectTelemetryHandler(k8sExec, os.Getenv("PROMETHEUS_URL"), deploymentRepository)
		logger.Info(
			"configured Kubernetes deployment executor and verified API connectivity",
			"executor",
			"kubernetes",
			"cluster",
			cfg.EKSClusterName,
			"region",
			cfg.AWSRegion,
			"namespace",
			cfg.KubernetesNamespace,
		)
	} else if cfg.DeploymentExecutor == "simulated" || cfg.AppEnv == "development" || cfg.AppEnv == "test" {
		deploymentRepository.SetExecutionMode("simulated")
		deploymentExec = executor.SimulatedExecutor{
			ExecutionDelay: 2 * time.Second,
			ShouldFail:     false,
		}
		logger.Info("configured local deployment executor", "executor", "simulated")
	} else {
		logger.Error(
			"cannot initialize executor: production mode requires Kubernetes configuration and cannot use simulation",
			"env",
			cfg.AppEnv,
			"executor",
			cfg.DeploymentExecutor,
		)
		os.Exit(1)
	}

	shutdownContext, stop := signal.NotifyContext(
		context.Background(),
		syscall.SIGINT,
		syscall.SIGTERM,
	)
	defer stop()

	workersDone := worker.StartDurable(shutdownContext, 2, deploymentRepository, deploymentExec, deploymentMetrics, logger)

	deploymentHandler := handler.NewDeploymentHandler(
		deploymentService,
	)

	queuedDeploymentHandler := handler.NewQueuedDeploymentHandler(
		deploymentService,
		nil,
		deploymentRepository,
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
		telemetryHandler,
	)

	authenticatedRouter := handler.NewAuthenticatedRouter(router,
		os.Getenv("CLOUDFORGE_FRONTEND_KEY"), os.Getenv("CLOUDFORGE_AIOPS_DEPLOYMENT_KEY"), identity.ProjectAccess{DB: pool})

	instrumentedRouter := metrics.Middleware(
		serviceMetrics,
	)(authenticatedRouter)

	server := &http.Server{
		Addr: ":" + strconv.Itoa(cfg.ServerPort),

		Handler: instrumentedRouter,

		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

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
		)

		serverErrors <- server.ListenAndServe()
	}()

	serverFailed := false
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

			serverFailed = true
		}

	case <-shutdownContext.Done():
		logger.Info(
			"shutdown signal received",
		)
	}

	stop()

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

		os.Exit(1)
	}

	select {
	case <-workersDone:
	case <-shutdownCtx.Done():
		logger.Error("deployment worker shutdown timed out", "error", shutdownCtx.Err())
		os.Exit(1)
	}

	if serverFailed {
		os.Exit(1)
	}

	logger.Info(
		"deployment service stopped successfully",
	)
}
