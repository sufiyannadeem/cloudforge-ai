package executor

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestSimulatedExecutorSuccess(t *testing.T) {
	deploymentID := uuid.New()

	executor := SimulatedExecutor{
		ExecutionDelay: time.Millisecond,
	}

	result, err := executor.Execute(context.Background(), deploymentID)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if result.DeploymentID != deploymentID {
		t.Fatalf("unexpected deployment ID: %v", result.DeploymentID)
	}

	if result.Status != "succeeded" {
		t.Fatalf("expected succeeded, got %s", result.Status)
	}
}

func TestSimulatedExecutorFailure(t *testing.T) {
	executor := SimulatedExecutor{
		ExecutionDelay: time.Millisecond,
		ShouldFail:     true,
	}

	result, err := executor.Execute(context.Background(), uuid.New())
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	if result.Status != "failed" {
		t.Fatalf("expected failed, got %s", result.Status)
	}
}

func TestSimulatedExecutorInvalidID(t *testing.T) {
	executor := SimulatedExecutor{}

	_, err := executor.Execute(context.Background(), uuid.Nil)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
}

func TestSimulatedExecutorCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	executor := SimulatedExecutor{
		ExecutionDelay: time.Second,
	}

	_, err := executor.Execute(ctx, uuid.New())
	if err == nil {
		t.Fatal("expected cancellation error, got nil")
	}
}
