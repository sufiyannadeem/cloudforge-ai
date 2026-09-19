package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type runnerExecutor struct {
	shouldFail bool
}

func (e runnerExecutor) Execute(
	ctx context.Context,
	deploymentID uuid.UUID,
) (executor.Result, error) {
	if e.shouldFail {
		return executor.Result{
			DeploymentID: deploymentID,
			Status:       "failed",
			Message:      "test failure",
		}, errors.New("test execution failure")
	}

	return executor.Result{
		DeploymentID: deploymentID,
		Status:       "succeeded",
		Message:      "test success",
		Duration:     time.Millisecond,
	}, nil
}

func newRunnerStore() (*mockDeploymentStore, *model.Deployment) {
	currentDeployment := existingDeployment()

	store := &mockDeploymentStore{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return currentDeployment, nil
		},
	}

	store.updateFunc = func(
		ctx context.Context,
		deployment model.Deployment,
	) error {
		currentDeployment = deployment
		store.updatedDeployment = deployment
		return nil
	}

	return store, &currentDeployment
}

func TestDeploymentRunnerSuccess(t *testing.T) {
	store, deployment := newRunnerStore()

	deploymentService := NewDeploymentService(store)

	runner, err := NewDeploymentRunner(
		deploymentService,
		runnerExecutor{},
		nil,
	)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	err = runner.Run(
		context.Background(),
		deployment.ID,
	)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if store.updatedDeployment.Status != model.DeploymentStatusSucceeded {
		t.Fatalf(
			"expected succeeded status, got %s",
			store.updatedDeployment.Status,
		)
	}
}

func TestDeploymentRunnerFailure(t *testing.T) {
	store, deployment := newRunnerStore()

	deploymentService := NewDeploymentService(store)

	runner, err := NewDeploymentRunner(
		deploymentService,
		runnerExecutor{
			shouldFail: true,
		},
		nil,
	)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	err = runner.Run(
		context.Background(),
		deployment.ID,
	)
	if err == nil {
		t.Fatal("expected execution error, got nil")
	}

	if store.updatedDeployment.Status != model.DeploymentStatusFailed {
		t.Fatalf(
			"expected failed status, got %s",
			store.updatedDeployment.Status,
		)
	}
}

func TestNewDeploymentRunnerValidation(t *testing.T) {
	store := &mockDeploymentStore{}
	deploymentService := NewDeploymentService(store)

	_, err := NewDeploymentRunner(
		nil,
		runnerExecutor{},
		nil,
	)
	if err == nil {
		t.Fatal("expected error for nil deployment service")
	}

	_, err = NewDeploymentRunner(
		deploymentService,
		nil,
		nil,
	)
	if err == nil {
		t.Fatal("expected error for nil executor")
	}
}
