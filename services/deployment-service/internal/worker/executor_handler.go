package worker

import (
	"context"
	"log/slog"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
)

// ExecutorHandler adapts an executor to the worker Handler interface.
type ExecutorHandler struct {
	executor executor.Executor
	logger   *slog.Logger
}

// NewExecutorHandler creates a worker-compatible executor handler.
func NewExecutorHandler(
	executorInstance executor.Executor,
	logger *slog.Logger,
) *ExecutorHandler {
	if logger == nil {
		logger = slog.Default()
	}

	return &ExecutorHandler{
		executor: executorInstance,
		logger:   logger,
	}
}

// Handle executes a deployment job.
func (h *ExecutorHandler) Handle(
	ctx context.Context,
	job Job,
) error {
	result, err := h.executor.Execute(ctx, job.DeploymentID)

	if err != nil {
		h.logger.Error(
			"deployment execution failed",
			"deployment_id",
			job.DeploymentID,
			"status",
			result.Status,
			"message",
			result.Message,
			"error",
			err,
		)

		return err
	}

	h.logger.Info(
		"deployment execution succeeded",
		"deployment_id",
		result.DeploymentID,
		"status",
		result.Status,
		"message",
		result.Message,
		"duration",
		result.Duration,
	)

	return nil
}
