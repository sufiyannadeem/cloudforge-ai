package worker

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/metrics"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
)

const executionLeaseTTL = 30 * time.Second

type ExecutionStore interface {
	ClaimExecution(context.Context, time.Duration) (repository.ExecutionLease, error)
	RenewExecution(context.Context, repository.ExecutionLease, time.Duration) error
	BeginExecution(context.Context, repository.ExecutionLease) error
	FinishExecution(context.Context, repository.ExecutionLease, error) error
}

func StartDurable(ctx context.Context, count int, store ExecutionStore, exec executor.Executor, stats *metrics.DeploymentMetrics, logger *slog.Logger) <-chan struct{} {
	done := make(chan struct{})
	var workers sync.WaitGroup
	for range count {
		workers.Go(func() {
			for ctx.Err() == nil {
				claimCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
				lease, err := store.ClaimExecution(claimCtx, executionLeaseTTL)
				cancel()
				if err == nil && lease.Token != uuid.Nil {
					runLeased(ctx, store, exec, lease, stats, logger)
					continue
				}
				if err != nil && ctx.Err() == nil {
					logger.Error("claim deployment execution", "error", err)
				}
				if !waitFor(ctx, time.Second) {
					return
				}
			}
		})
	}
	go func() {
		workers.Wait()
		close(done)
	}()
	return done
}

func runLeased(ctx context.Context, store ExecutionStore, exec executor.Executor, lease repository.ExecutionLease, stats *metrics.DeploymentMetrics, logger *slog.Logger) {
	runCtx, cancel := context.WithCancel(ctx)
	renewed := make(chan struct{})
	go func() {
		defer close(renewed)
		for waitFor(runCtx, executionLeaseTTL/3) {
			renewCtx, cancelRenew := context.WithTimeout(runCtx, 5*time.Second)
			err := store.RenewExecution(renewCtx, lease, executionLeaseTTL)
			cancelRenew()
			if err != nil {
				cancel()
				return
			}
		}
	}()
	defer func() {
		cancel()
		<-renewed
	}()

	started := time.Now()
	if stats != nil {
		stats.DeploymentStarted()
	}
	status := "cancelled"
	defer func() {
		if stats != nil {
			stats.DeploymentCompleted(lease.Environment, status, time.Since(started))
		}
	}()

	var executionErr error
	if lease.ModeMismatch {
		executionErr = errors.New("execution mode changed; manual reconciliation required")
	} else if lease.Reconcile {
		executionErr = reconcileExecution(runCtx, exec, lease.DeploymentID)
	} else {
		var claimErr error
		claim := func() error {
			beginCtx, cancelBegin := context.WithTimeout(runCtx, 5*time.Second)
			defer cancelBegin()
			claimErr = store.BeginExecution(beginCtx, lease)
			return claimErr
		}
		if guarded, ok := exec.(interface {
			ExecuteWithClaim(context.Context, uuid.UUID, func() error) (executor.Result, error)
		}); ok {
			_, executionErr = guarded.ExecuteWithClaim(runCtx, lease.DeploymentID, claim)
		} else if claim() == nil && runCtx.Err() == nil {
			_, executionErr = exec.Execute(runCtx, lease.DeploymentID)
		}
		if claimErr != nil {
			logger.Warn("deployment execution claim lost", "deployment_id", lease.DeploymentID, "error", claimErr)
			return
		}
	}

	if runCtx.Err() != nil {
		// Leave the lease and attempt recoverable after shutdown or ownership loss.
		return
	}
	finishCtx, cancelFinish := context.WithTimeout(runCtx, 5*time.Second)
	defer cancelFinish()
	if err := store.FinishExecution(finishCtx, lease, executionErr); err != nil {
		logger.Error("finish deployment execution", "deployment_id", lease.DeploymentID, "error", err)
		return
	}
	status = "succeeded"
	if executionErr != nil {
		status = "failed"
		logger.Warn("deployment execution failed", "deployment_id", lease.DeploymentID, "error", executionErr)
	}
}

func reconcileExecution(ctx context.Context, exec executor.Executor, id uuid.UUID) error {
	reconciler, ok := exec.(interface {
		Reconcile(context.Context, uuid.UUID) error
	})
	if !ok {
		return fmt.Errorf("manual intervention required: executor cannot reconcile uncertain execution")
	}

	var err error
	for attempt := range 5 {
		if attempt > 0 && !waitFor(ctx, time.Second<<attempt) {
			return ctx.Err()
		}
		checkCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
		err = reconciler.Reconcile(checkCtx, id)
		cancel()
		if err == nil {
			return nil
		}
	}
	return fmt.Errorf("manual intervention required: Kubernetes state could not be confirmed: %w", err)
}

func waitFor(ctx context.Context, delay time.Duration) bool {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return ctx.Err() == nil
	}
}
