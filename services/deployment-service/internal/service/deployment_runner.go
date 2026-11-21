package service

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/metrics"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
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
}

type DeploymentRunner struct {
	deploymentService *DeploymentService
	attemptManager    DeploymentAttemptManager
	executor          executor.Executor
	logger            *slog.Logger
	metrics           *metrics.DeploymentMetrics
}

func NewDeploymentRunner(
	deploymentService *DeploymentService,
	deploymentExecutor executor.Executor,
	logger *slog.Logger,
) (*DeploymentRunner, error) {
	return NewDeploymentRunnerWithAttemptsAndMetrics(
		deploymentService,
		nil,
		deploymentExecutor,
		logger,
		nil,
	)
}

func NewDeploymentRunnerWithAttempts(
	deploymentService *DeploymentService,
	attemptManager DeploymentAttemptManager,
	deploymentExecutor executor.Executor,
	logger *slog.Logger,
) (*DeploymentRunner, error) {
	return NewDeploymentRunnerWithAttemptsAndMetrics(
		deploymentService,
		attemptManager,
		deploymentExecutor,
		logger,
		nil,
	)
}

func NewDeploymentRunnerWithAttemptsAndMetrics(
	deploymentService *DeploymentService,
	attemptManager DeploymentAttemptManager,
	deploymentExecutor executor.Executor,
	logger *slog.Logger,
	deploymentMetrics *metrics.DeploymentMetrics,
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
		metrics:           deploymentMetrics,
	}, nil
}

func (r *DeploymentRunner) Run(
	ctx context.Context,
	deploymentID uuid.UUID,
) error {
	if deploymentID == uuid.Nil {
		return ErrInvalidDeploymentID
	}

	deployment, err := r.deploymentService.GetByID(
		ctx,
		deploymentID,
	)
	if err != nil {
		return fmt.Errorf(
			"get deployment before execution: %w",
			err,
		)
	}

	if deployment.Status == model.DeploymentStatusPending {
		queued := model.DeploymentStatusQueued
		deployment, err = r.deploymentService.update(ctx, deployment, model.UpdateDeploymentInput{Status: &queued})
		if err != nil {
			return fmt.Errorf("mark deployment as queued: %w", err)
		}
	}

	if deployment.Status != model.DeploymentStatusQueued {
		return fmt.Errorf("%w: execution requires a queued deployment, got %s", ErrInvalidDeploymentTransition, deployment.Status)
	}
	running := model.DeploymentStatusRunning
	if _, err := r.deploymentService.update(ctx, deployment, model.UpdateDeploymentInput{Status: &running}); err != nil {
		return fmt.Errorf("claim deployment execution: %w", err)
	}

	attempt, err := r.startAttempt(ctx, deploymentID)
	if err != nil {
		cleanupCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
		defer cancel()
		return errors.Join(
			fmt.Errorf("start deployment attempt: %w", err),
			r.updateStatus(cleanupCtx, deploymentID, model.DeploymentStatusFailed),
		)
	}

	startTime := time.Now()

	if r.metrics != nil {
		r.metrics.DeploymentStarted()
	}

	metricsCompleted := false

	defer func() {
		if !metricsCompleted && r.metrics != nil {
			r.metrics.DeploymentCompleted(
				deployment.Environment,
				"failed",
				time.Since(startTime),
			)
		}
	}()

	result, executionErr := r.executor.Execute(
		ctx,
		deploymentID,
	)

	writeCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()

	if executionErr != nil {
		r.logger.Error(
			"deployment execution failed",
			"deployment_id",
			deploymentID,
			"error",
			executionErr,
		)

		attemptStatus := model.AttemptStatusFailed

		metricStatus := "failed"

		if errors.Is(ctx.Err(), context.Canceled) ||
			errors.Is(ctx.Err(), context.DeadlineExceeded) {
			attemptStatus = model.AttemptStatusCancelled
			metricStatus = "cancelled"
		}

		r.completeAttempt(
			writeCtx,
			attempt,
			attemptStatus,
			executionErr,
			startTime,
		)

		statusErr := r.updateStatus(
			writeCtx,
			deploymentID,
			model.DeploymentStatusFailed,
		)

		if r.metrics != nil {
			r.metrics.DeploymentCompleted(
				deployment.Environment,
				metricStatus,
				time.Since(startTime),
			)

			metricsCompleted = true
		}

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
		writeCtx,
		deploymentID,
		model.DeploymentStatusSucceeded,
	); err != nil {
		r.completeAttempt(
			writeCtx,
			attempt,
			model.AttemptStatusFailed,
			err,
			startTime,
		)

		if r.metrics != nil {
			r.metrics.DeploymentCompleted(
				deployment.Environment,
				"failed",
				time.Since(startTime),
			)

			metricsCompleted = true
		}

		return fmt.Errorf(
			"mark deployment as succeeded: %w",
			err,
		)
	}

	r.completeAttempt(
		writeCtx,
		attempt,
		model.AttemptStatusSucceeded,
		nil,
		startTime,
	)

	if r.metrics != nil {
		r.metrics.DeploymentCompleted(
			deployment.Environment,
			"succeeded",
			time.Since(startTime),
		)

		metricsCompleted = true
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

func (r *DeploymentRunner) startAttempt(
	ctx context.Context,
	deploymentID uuid.UUID,
) (*model.DeploymentAttempt, error) {
	if r.attemptManager == nil {
		return nil, nil
	}

	now := time.Now()

	attempt := &model.DeploymentAttempt{
		ID:           uuid.New(),
		DeploymentID: deploymentID,
		Status:       model.AttemptStatusRunning,
		StartedAt:    now,
		CreatedAt:    now,
	}

	if err := r.attemptManager.Create(
		ctx,
		*attempt,
	); err != nil {
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

	if err := r.attemptManager.Update(
		ctx,
		*attempt,
	); err != nil {
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
	for {
		_, err := r.deploymentService.Update(ctx, deploymentID, model.UpdateDeploymentInput{Status: &status})
		if !errors.Is(err, repository.ErrDeploymentConflict) {
			return err
		}
		if err := ctx.Err(); err != nil {
			return err
		}
	}
}
