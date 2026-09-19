package executor

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// Result represents the result of a deployment execution.
type Result struct {
	DeploymentID uuid.UUID
	Status       string
	Message      string
	Duration     time.Duration
}

// Executor runs deployment operations.
type Executor interface {
	Execute(ctx context.Context, deploymentID uuid.UUID) (Result, error)
}

// SimulatedExecutor is a local executor used for development and testing.
type SimulatedExecutor struct {
	ExecutionDelay time.Duration
	ShouldFail     bool
}

// Execute simulates a deployment execution.
func (e SimulatedExecutor) Execute(
	ctx context.Context,
	deploymentID uuid.UUID,
) (Result, error) {
	start := time.Now()

	if deploymentID == uuid.Nil {
		return Result{}, errors.New("deployment ID is required")
	}

	delay := e.ExecutionDelay
	if delay <= 0 {
		delay = 100 * time.Millisecond
	}

	timer := time.NewTimer(delay)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return Result{}, fmt.Errorf("deployment cancelled: %w", ctx.Err())

	case <-timer.C:
	}

	if e.ShouldFail {
		return Result{
			DeploymentID: deploymentID,
			Status:       "failed",
			Message:      "simulated deployment failure",
			Duration:     time.Since(start),
		}, errors.New("simulated deployment failure")
	}

	return Result{
		DeploymentID: deploymentID,
		Status:       "succeeded",
		Message:      "deployment completed successfully",
		Duration:     time.Since(start),
	}, nil
}
