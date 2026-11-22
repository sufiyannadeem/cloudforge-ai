package repository

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func setupLeaseTestDB(t *testing.T) (context.Context, *pgxpool.Pool, *ResourceRepository, model.InfrastructureResource) {
	t.Helper()
	if testPool == nil {
		t.Skip("TEST_DATABASE_URL not set; skipping integration test")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	t.Cleanup(cancel)

	schema := pgx.Identifier{"lease_" + uuid.NewString()}.Sanitize()
	if _, err := testPool.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatalf("create schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = testPool.Exec(cleanupCtx, "DROP SCHEMA "+schema+" CASCADE")
	})

	config := testPool.Config()
	config.ConnConfig.RuntimeParams["search_path"] = schema
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("create isolated pool: %v", err)
	}
	t.Cleanup(pool.Close)

	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatalf("run migrations: %v", err)
	}

	repo := NewResourceRepository(pool)
	res := newTestResource()
	res.Status = model.ResourceStatusPending
	if err := repo.Create(ctx, res); err != nil {
		t.Fatalf("create resource: %v", err)
	}

	return ctx, pool, repo, res
}

func TestAcquireExecutionLeaseAtomicMutualExclusion(t *testing.T) {
	ctx, _, repo, res := setupLeaseTestDB(t)

	// Worker 1 acquires lease for 5 seconds
	lease1, err := repo.AcquireExecutionLease(ctx, res.ID, "replica-1:worker-1", "plan", 5*time.Second)
	if err != nil {
		t.Fatalf("expected worker 1 to acquire lease: %v", err)
	}
	if lease1.FencingToken != 1 {
		t.Fatalf("expected initial fencing token 1, got %d", lease1.FencingToken)
	}
	if lease1.Operation != "plan" {
		t.Fatalf("expected operation 'plan', got %s", lease1.Operation)
	}

	// Worker 2 attempts concurrent acquisition while lease1 is active
	_, err = repo.AcquireExecutionLease(ctx, res.ID, "replica-2:worker-2", "apply", 5*time.Second)
	if !errors.Is(err, ErrResourceConflict) {
		t.Fatalf("expected ErrResourceConflict for concurrent acquisition, got %v", err)
	}

	// Concurrent race with multiple goroutines: exactly 0 new acquisitions succeed
	var wg sync.WaitGroup
	errs := make(chan error, 10)
	for i := range 10 {
		wg.Add(1)
		go func(workerNum int) {
			defer wg.Done()
			owner := uuid.NewString()
			_, aerr := repo.AcquireExecutionLease(ctx, res.ID, owner, "plan", 5*time.Second)
			errs <- aerr
		}(i)
	}
	wg.Wait()
	close(errs)

	for e := range errs {
		if !errors.Is(e, ErrResourceConflict) {
			t.Fatalf("expected ErrResourceConflict during active lease, got %v", e)
		}
	}
}

func TestHeartbeatRenewsLease(t *testing.T) {
	ctx, _, repo, res := setupLeaseTestDB(t)

	lease, err := repo.AcquireExecutionLease(ctx, res.ID, "replica-1:worker-1", "plan", 500*time.Millisecond)
	if err != nil {
		t.Fatalf("acquire lease: %v", err)
	}
	origExpiry := lease.LeaseExpiresAt

	time.Sleep(100 * time.Millisecond)

	// Heartbeat extends lease
	if err := repo.HeartbeatExecutionLease(ctx, res.ID, lease.OwnerID, lease.FencingToken, 2*time.Second); err != nil {
		t.Fatalf("heartbeat: %v", err)
	}

	updated, err := repo.GetExecutionLease(ctx, res.ID)
	if err != nil {
		t.Fatalf("get lease: %v", err)
	}
	if !updated.LeaseExpiresAt.After(origExpiry) {
		t.Fatalf("expected expiry %v to be after original %v", updated.LeaseExpiresAt, origExpiry)
	}
}

func TestLeaseExpiryAndStaleExecutionRecovery(t *testing.T) {
	ctx, _, repo, res := setupLeaseTestDB(t)

	// Worker 1 acquires short lease (200ms)
	lease1, err := repo.AcquireExecutionLease(ctx, res.ID, "replica-1:worker-1", "plan", 200*time.Millisecond)
	if err != nil {
		t.Fatalf("worker 1 acquire: %v", err)
	}

	// Wait for lease to expire
	time.Sleep(250 * time.Millisecond)

	// Worker 2 safely recovers the stale execution: acquisition must succeed
	lease2, err := repo.AcquireExecutionLease(ctx, res.ID, "replica-2:worker-2", "plan", 5*time.Second)
	if err != nil {
		t.Fatalf("worker 2 stale recovery: %v", err)
	}
	if lease2.FencingToken <= lease1.FencingToken {
		t.Fatalf("expected fencing token increment (%d > %d)", lease2.FencingToken, lease1.FencingToken)
	}
	if lease2.OwnerID != "replica-2:worker-2" {
		t.Fatalf("expected new owner, got %s", lease2.OwnerID)
	}

	// Worker 1 attempts heartbeat with stale fencing token -> rejected with ErrLeaseLost
	err = repo.HeartbeatExecutionLease(ctx, res.ID, lease1.OwnerID, lease1.FencingToken, 5*time.Second)
	if !errors.Is(err, ErrLeaseLost) {
		t.Fatalf("expected ErrLeaseLost for fenced-out worker 1 heartbeat, got %v", err)
	}

	// Worker 1 attempts release with stale fencing token -> rejected with ErrLeaseLost
	err = repo.ReleaseExecutionLease(ctx, res.ID, lease1.OwnerID, lease1.FencingToken)
	if !errors.Is(err, ErrLeaseLost) {
		t.Fatalf("expected ErrLeaseLost for fenced-out worker 1 release, got %v", err)
	}

	// Worker 2 releases valid lease -> succeeds
	if err := repo.ReleaseExecutionLease(ctx, res.ID, lease2.OwnerID, lease2.FencingToken); err != nil {
		t.Fatalf("worker 2 release: %v", err)
	}

	// After release, new worker can acquire immediately
	lease3, err := repo.AcquireExecutionLease(ctx, res.ID, "replica-3:worker-3", "apply", 5*time.Second)
	if err != nil {
		t.Fatalf("worker 3 acquire after release: %v", err)
	}
	if lease3.FencingToken <= lease2.FencingToken {
		t.Fatalf("expected fencing token increment (%d > %d)", lease3.FencingToken, lease2.FencingToken)
	}
}
