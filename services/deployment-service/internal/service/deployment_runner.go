package service

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

// DeploymentRunner coordinates deployment status updates and execution.
type DeploymentRunner struct {
	deploymentService *DeploymentService
	executor          executor.Executor
	logger            *slog.Logger
}

// NewDeploymentRunner creates a deployment runner.
func NewDeploymentRunner(
	deploymentService *DeploymentService,
	deploymentExecutor executor.Executor,
	logger *slog.Logger,
) (*DeploymentRunner, error) {
	if deploymentService == nil {
		return nil, errors.New("deployment service is required")
	}

	if deploymentExecutor == nil {
		return nil, errors.New("deployment executor is required")
	}

	if logger == nil {
		logger = slog.Default()
	}

	return &DeploymentRunner{
		deploymentService: deploymentService,
		executor:          deploymentExecutor,
		logger:            logger,
	}, nil
}

// Run executes a deployment and updates its status.
func (r *DeploymentRunner) Run(
	ctx context.Context,
	deploymentID uuid.UUID,
) error {
	if deploymentID == uuid.Nil {
		return ErrInvalidDeploymentID
	}

	if err := r.updateStatus(
		ctx,
		deploymentID,
		model.DeploymentStatusQueued,
	); err != nil {
		return fmt.Errorf("mark deployment as queued: %w", err)
	}

	if err := r.updateStatus(
		ctx,
		deploymentID,
		model.DeploymentStatusRunning,
	); err != nil {
		return fmt.Errorf("mark deployment as running: %w", err)
	}

	result, executionErr := r.executor.Execute(ctx, deploymentID)

	if executionErr != nil {
		r.logger.Error(
			"deployment execution failed",
			"deployment_id",
			deploymentID,
			"error",
			executionErr,
		)

		statusErr := r.updateStatus(
			ctx,
			deploymentID,
			model.DeploymentStatusFailed,
		)

		if statusErr != nil {
			return fmt.Errorf(
				"deployment failed: %v; update failed status: %w",
				executionErr,
				statusErr,
			)
		}

		return executionErr
	}

	if err := r.updateStatus(
		ctx,
		deploymentID,
		model.DeploymentStatusSucceeded,
	); err != nil {
		return fmt.Errorf("mark deployment as succeeded: %w", err)
	}

	r.logger.Info(
		"deployment completed",
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

func (r *DeploymentRunner) updateStatus(
	ctx context.Context,
	deploymentID uuid.UUID,
	status model.DeploymentStatus,
) error {
	_, err := r.deploymentService.Update(
		ctx,
		deploymentID,
		model.UpdateDeploymentInput{
			Status: &status,
		},
	)

	return err
}
