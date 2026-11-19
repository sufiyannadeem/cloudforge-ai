package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
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

type mockAttemptStore struct {
	createdAttempts []model.DeploymentAttempt
	updatedAttempts []model.DeploymentAttempt
}

func (m *mockAttemptStore) Create(ctx context.Context, attempt model.DeploymentAttempt) error {
	m.createdAttempts = append(m.createdAttempts, attempt)
	return nil
}

func (m *mockAttemptStore) Update(ctx context.Context, attempt model.DeploymentAttempt) error {
	m.updatedAttempts = append(m.updatedAttempts, attempt)
	return nil
}

func TestDeploymentRunnerRolloutTimeoutFails(t *testing.T) {
	store, deployment := newRunnerStore()
	deploymentService := NewDeploymentService(store)

	timeoutExecutor := runnerExecutor{shouldFail: true}

	runner, err := NewDeploymentRunner(deploymentService, timeoutExecutor, nil)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	err = runner.Run(context.Background(), deployment.ID)
	if err == nil {
		t.Fatal("expected error on timeout, got nil")
	}

	if store.updatedDeployment.Status != model.DeploymentStatusFailed {
		t.Fatalf("expected deployment status failed after timeout, got: %s", store.updatedDeployment.Status)
	}
}

func TestDeploymentRunnerRollbackWithAttemptsSuccess(t *testing.T) {
	store, deployment := newRunnerStore()
	deploymentService := NewDeploymentService(store)
	attemptStore := &mockAttemptStore{}

	runner, err := NewDeploymentRunnerWithAttempts(
		deploymentService,
		attemptStore,
		runnerExecutor{shouldFail: false},
		nil,
	)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	err = runner.Run(context.Background(), deployment.ID)
	if err != nil {
		t.Fatalf("expected no error running rollback deployment, got %v", err)
	}

	if store.updatedDeployment.Status != model.DeploymentStatusSucceeded {
		t.Fatalf("expected deployment status succeeded, got %s", store.updatedDeployment.Status)
	}

	if len(attemptStore.createdAttempts) != 1 {
		t.Fatalf("expected 1 created attempt, got %d", len(attemptStore.createdAttempts))
	}

	if len(attemptStore.updatedAttempts) != 1 {
		t.Fatalf("expected 1 updated attempt, got %d", len(attemptStore.updatedAttempts))
	}

	if attemptStore.updatedAttempts[0].Status != model.AttemptStatusSucceeded {
		t.Fatalf("expected attempt status succeeded, got %s", attemptStore.updatedAttempts[0].Status)
	}
}

func TestDeploymentRunnerRollbackWithAttemptsFailure(t *testing.T) {
	store, deployment := newRunnerStore()
	deploymentService := NewDeploymentService(store)
	attemptStore := &mockAttemptStore{}

	runner, err := NewDeploymentRunnerWithAttempts(
		deploymentService,
		attemptStore,
		runnerExecutor{shouldFail: true},
		nil,
	)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	err = runner.Run(context.Background(), deployment.ID)
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	if store.updatedDeployment.Status != model.DeploymentStatusFailed {
		t.Fatalf("expected deployment status failed, got %s", store.updatedDeployment.Status)
	}

	if len(attemptStore.updatedAttempts) != 1 {
		t.Fatalf("expected 1 updated attempt, got %d", len(attemptStore.updatedAttempts))
	}

	if attemptStore.updatedAttempts[0].Status != model.AttemptStatusFailed {
		t.Fatalf("expected attempt status failed, got %s", attemptStore.updatedAttempts[0].Status)
	}

	if attemptStore.updatedAttempts[0].ErrorMessage == nil || *attemptStore.updatedAttempts[0].ErrorMessage == "" {
		t.Fatal("expected attempt error message to be recorded")
	}
}

type blockingRunnerExecutor struct {
	entered chan struct{}
	release chan struct{}
}

func (e blockingRunnerExecutor) Execute(ctx context.Context, id uuid.UUID) (executor.Result, error) {
	close(e.entered)
	select {
	case <-e.release:
		return runnerExecutor{}.Execute(ctx, id)
	case <-ctx.Done():
		return executor.Result{}, ctx.Err()
	}
}

func TestDeploymentRunnerRejectsDuplicateExecution(t *testing.T) {
	store, deployment := newRunnerStore()
	deployment.Status = model.DeploymentStatusQueued
	id := deployment.ID
	attempts := &mockAttemptStore{}
	exec := blockingRunnerExecutor{entered: make(chan struct{}), release: make(chan struct{})}
	runner, err := NewDeploymentRunnerWithAttempts(NewDeploymentService(store), attempts, exec, nil)
	if err != nil {
		t.Fatal(err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- runner.Run(ctx, id) }()
	select {
	case <-exec.entered:
	case err := <-done:
		t.Fatalf("first runner exited before execution: %v", err)
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}

	err = runner.Run(ctx, id)
	close(exec.release)
	if firstErr := <-done; firstErr != nil {
		t.Fatal(firstErr)
	}
	if !errors.Is(err, ErrInvalidDeploymentTransition) {
		t.Fatalf("expected duplicate execution rejection, got %v", err)
	}
	if len(attempts.createdAttempts) != 1 || len(attempts.updatedAttempts) != 1 ||
		deployment.Status != model.DeploymentStatusSucceeded {
		t.Fatal("expected one completed attempt and a succeeded deployment")
	}
}

func TestDeploymentRunnerStopsOnClaimConflict(t *testing.T) {
	store, deployment := newRunnerStore()
	deployment.Status = model.DeploymentStatusQueued
	store.updateFunc = func(context.Context, model.Deployment) error {
		return repository.ErrDeploymentConflict
	}
	attempts := &mockAttemptStore{}
	exec := blockingRunnerExecutor{entered: make(chan struct{}), release: make(chan struct{})}
	close(exec.release)
	runner, err := NewDeploymentRunnerWithAttempts(NewDeploymentService(store), attempts, exec, nil)
	if err != nil {
		t.Fatal(err)
	}

	if err := runner.Run(context.Background(), deployment.ID); !errors.Is(err, repository.ErrDeploymentConflict) {
		t.Fatalf("expected claim conflict, got %v", err)
	}
	select {
	case <-exec.entered:
		t.Fatal("executor ran after losing the claim")
	default:
	}
	if len(attempts.createdAttempts) != 0 || deployment.Status != model.DeploymentStatusQueued {
		t.Fatal("failed claim changed deployment or attempt history")
	}
}
