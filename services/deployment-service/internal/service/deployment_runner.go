package service

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type DeploymentAttemptManager interface {
	Create(
		ctx context.Context,
		attempt model.DeploymentAttempt,
	) error

	Update(
		ctx context.Context,
		attempt model.DeploymentAttempt,
	) error

	GetNextAttemptNumber(
		ctx context.Context,
		deploymentID uuid.UUID,
	) (int, error)
}

type DeploymentRunner struct {
	deploymentService *DeploymentService
	attemptManager    DeploymentAttemptManager
	executor          executor.Executor
	logger            *slog.Logger
}

func NewDeploymentRunner(
	deploymentService *DeploymentService,
	deploymentExecutor executor.Executor,
	logger *slog.Logger,
) (*DeploymentRunner, error) {
	return NewDeploymentRunnerWithAttempts(
		deploymentService,
		nil,
		deploymentExecutor,
		logger,
	)
}

func NewDeploymentRunnerWithAttempts(
	deploymentService *DeploymentService,
	attemptManager DeploymentAttemptManager,
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
		attemptManager:    attemptManager,
		executor:          deploymentExecutor,
		logger:            logger,
	}, nil
}

func (r *DeploymentRunner) Run(
	ctx context.Context,
	deploymentID uuid.UUID,
) error {
	if deploymentID == uuid.Nil {
		return ErrInvalidDeploymentID
	}

	attempt, err := r.startAttempt(ctx, deploymentID)
	if err != nil {
		return fmt.Errorf("start deployment attempt: %w", err)
	}

	startTime := time.Now()

	if err := r.updateStatus(
		ctx,
		deploymentID,
		model.DeploymentStatusQueued,
	); err != nil {
		r.completeAttempt(
			ctx,
			attempt,
			model.AttemptStatusFailed,
			err,
			startTime,
		)

		return fmt.Errorf("mark deployment as queued: %w", err)
	}

	if err := r.updateStatus(
		ctx,
		deploymentID,
		model.DeploymentStatusRunning,
	); err != nil {
		r.completeAttempt(
			ctx,
			attempt,
			model.AttemptStatusFailed,
			err,
			startTime,
		)

		return fmt.Errorf("mark deployment as running: %w", err)
	}

	result, executionErr := r.executor.Execute(
		ctx,
		deploymentID,
	)

	if executionErr != nil {
		r.logger.Error(
			"deployment execution failed",
			"deployment_id",
			deploymentID,
			"error",
			executionErr,
		)

		attemptStatus := model.AttemptStatusFailed

		if errors.Is(ctx.Err(), context.Canceled) ||
			errors.Is(ctx.Err(), context.DeadlineExceeded) {
			attemptStatus = model.AttemptStatusCancelled
		}

		r.completeAttempt(
			ctx,
			attempt,
			attemptStatus,
			executionErr,
			startTime,
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
		r.completeAttempt(
			ctx,
			attempt,
			model.AttemptStatusFailed,
			err,
			startTime,
		)

		return fmt.Errorf(
			"mark deployment as succeeded: %w",
			err,
		)
	}

	r.completeAttempt(
		ctx,
		attempt,
		model.AttemptStatusSucceeded,
		nil,
		startTime,
	)

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

func (r *DeploymentRunner) startAttempt(
	ctx context.Context,
	deploymentID uuid.UUID,
) (*model.DeploymentAttempt, error) {
	if r.attemptManager == nil {
		return nil, nil
	}

	attemptNumber, err := r.attemptManager.GetNextAttemptNumber(
		ctx,
		deploymentID,
	)

	if err != nil {
		return nil, err
	}

	now := time.Now()

	attempt := &model.DeploymentAttempt{
		ID:            uuid.New(),
		DeploymentID:  deploymentID,
		AttemptNumber: attemptNumber,
		Status:        model.AttemptStatusRunning,
		StartedAt:     now,
		CreatedAt:     now,
	}

	if err := r.attemptManager.Create(ctx, *attempt); err != nil {
		return nil, err
	}

	return attempt, nil
}

func (r *DeploymentRunner) completeAttempt(
	ctx context.Context,
	attempt *model.DeploymentAttempt,
	status model.DeploymentAttemptStatus,
	executionErr error,
	startTime time.Time,
) {
	if r.attemptManager == nil || attempt == nil {
		return
	}

	completedAt := time.Now()
	durationMs := completedAt.Sub(startTime).Milliseconds()

	attempt.Status = status
	attempt.CompletedAt = &completedAt
	attempt.DurationMs = &durationMs

	if executionErr != nil {
		message := executionErr.Error()
		attempt.ErrorMessage = &message
	}

	if err := r.attemptManager.Update(ctx, *attempt); err != nil {
		r.logger.Error(
			"failed to update deployment attempt",
			"attempt_id",
			attempt.ID,
			"deployment_id",
			attempt.DeploymentID,
			"error",
			err,
		)
	}
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
