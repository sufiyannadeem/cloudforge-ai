package worker

import (
	"context"
	"log/slog"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
)

type testExecutionStore struct {
	claims   atomic.Int32
	begun    atomic.Bool
	finished atomic.Bool
}

func (s *testExecutionStore) ClaimExecution(context.Context, time.Duration) (repository.ExecutionLease, error) {
	s.claims.Add(1)
	return repository.ExecutionLease{Token: uuid.New(), DeploymentID: uuid.New()}, nil
}
func (s *testExecutionStore) RenewExecution(context.Context, repository.ExecutionLease, time.Duration) error {
	return nil
}
func (s *testExecutionStore) BeginExecution(context.Context, repository.ExecutionLease) error {
	s.begun.Store(true)
	return nil
}
func (s *testExecutionStore) FinishExecution(context.Context, repository.ExecutionLease, error) error {
	s.finished.Store(true)
	return nil
}

type cancellingExecutor struct {
	entered chan struct{}
}

func (e cancellingExecutor) Execute(ctx context.Context, _ uuid.UUID) (executor.Result, error) {
	close(e.entered)
	<-ctx.Done()
	return executor.Result{}, ctx.Err()
}

func TestDurableShutdownCancelsExecutionAndLeavesLeaseRecoverable(t *testing.T) {
	store := &testExecutionStore{}
	exec := cancellingExecutor{entered: make(chan struct{})}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := StartDurable(ctx, 1, store, exec, nil, slog.Default())
	select {
	case <-exec.entered:
	case <-time.After(2 * time.Second):
		t.Fatal("worker did not start")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("worker did not shut down")
	}
	if store.claims.Load() != 1 || !store.begun.Load() || store.finished.Load() {
		t.Fatal("shutdown claimed more work or finalized an interrupted operation")
	}
}

type readOnlyRecoveryExecutor struct {
	t          *testing.T
	reconciled bool
}

func (e *readOnlyRecoveryExecutor) Execute(context.Context, uuid.UUID) (executor.Result, error) {
	e.t.Fatal("uncertain execution must be reconciled before any mutation")
	return executor.Result{}, nil
}

func (e *readOnlyRecoveryExecutor) Reconcile(context.Context, uuid.UUID) error {
	e.reconciled = true
	return nil
}

func TestDurableWorkerReconcilesAnUncertainExecution(t *testing.T) {
	store := &testExecutionStore{}
	exec := &readOnlyRecoveryExecutor{t: t}
	lease := repository.ExecutionLease{DeploymentID: uuid.New(), Token: uuid.New(), Reconcile: true}
	runLeased(context.Background(), store, exec, lease, nil, slog.Default())
	if !exec.reconciled || store.begun.Load() || !store.finished.Load() {
		t.Fatal("worker did not finalize recovery using read-only reconciliation")
	}
}

func TestDurableWorkerDoesNotReconcileWithDifferentExecutionMode(t *testing.T) {
	store := &testExecutionStore{}
	exec := &readOnlyRecoveryExecutor{t: t}
	lease := repository.ExecutionLease{DeploymentID: uuid.New(), Token: uuid.New(), Reconcile: true, ModeMismatch: true}
	runLeased(t.Context(), store, exec, lease, nil, slog.Default())
	if exec.reconciled || store.begun.Load() || !store.finished.Load() {
		t.Fatal("mismatched execution mode reached the executor")
	}
}

func TestDurableWorkerCannotSimulateProgressiveDelivery(t *testing.T) {
	store := &testExecutionStore{}
	exec := &readOnlyRecoveryExecutor{t: t}
	lease := repository.ExecutionLease{DeploymentID: uuid.New(), Token: uuid.New(), ProgressiveUnsupported: true}
	runLeased(t.Context(), store, exec, lease, nil, slog.Default())
	if exec.reconciled || store.begun.Load() || !store.finished.Load() {
		t.Fatal("unsupported strategy reached the executor")
	}
}
