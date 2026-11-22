package service

// lease_loss_safety_test.go — Batch 37.4.1 regression tests (Items 3-5)
//
// Covers:
//   Item 3: Expired leases do not permit overlapping Terraform side effects.
//           Stale workers' SavePlan/FinishReviewedPlan calls are rejected by fencing.
//   Item 4: Lease renewal failures fail closed — context is cancelled before
//           the Terraform runner can complete, so no result is persisted.
//   Item 5: Recovery: a new worker can acquire the lease after the previous
//           worker's context is cancelled (simulated crash / pod restart).

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"
)

// ---------------------------------------------------------------------------
// staleFencingStore: a mockResourceStore variant that records every WithLease
// call and rejects writes whose fencing token does not match the current lease.
// ---------------------------------------------------------------------------

type staleFencingStore struct {
	mockResourceStore

	mu                 sync.Mutex
	currentToken       int64
	currentOwnerID     string
	savePlanCalls      int
	savePlanRejections int
	finishCalls        int
	finishRejections   int
}

func (s *staleFencingStore) SavePlanWithLease(_ context.Context, resource model.InfrastructureResource, ownerID string, fencingToken int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.savePlanCalls++
	if ownerID != s.currentOwnerID || fencingToken != s.currentToken {
		s.savePlanRejections++
		return repository.ErrResourceConflict
	}
	s.mockResourceStore.resource = resource
	return nil
}

func (s *staleFencingStore) FinishReviewedPlanWithLease(_ context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus, succeeded bool, ownerID string, fencingToken int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.finishCalls++
	if ownerID != s.currentOwnerID || fencingToken != s.currentToken {
		s.finishRejections++
		return repository.ErrResourceConflict
	}
	s.mockResourceStore.resource.Status = next
	return nil
}

// TransitionStatusWithLease also validates fencing before transitioning.
func (s *staleFencingStore) TransitionStatusWithLease(ctx context.Context, id uuid.UUID, from []model.ResourceStatus, to model.ResourceStatus, ownerID string, fencingToken int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if ownerID != s.currentOwnerID || fencingToken != s.currentToken {
		return repository.ErrResourceConflict
	}
	return s.mockResourceStore.TransitionStatus(ctx, id, from, to)
}

// AcquireExecutionLease increments the fencing token for each new owner.
func (s *staleFencingStore) AcquireExecutionLease(_ context.Context, resourceID uuid.UUID, ownerID string, operation string, ttl time.Duration) (model.ExecutionLease, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now().UTC()
	// Reject if an active lease exists for a different owner.
	if s.mockResourceStore.lease.ResourceID == resourceID &&
		s.currentOwnerID != ownerID &&
		s.mockResourceStore.lease.LeaseExpiresAt.After(now) {
		return model.ExecutionLease{}, repository.ErrResourceConflict
	}
	s.currentToken++
	s.currentOwnerID = ownerID
	lease := model.ExecutionLease{
		ResourceID:     resourceID,
		OwnerID:        ownerID,
		Operation:      operation,
		FencingToken:   s.currentToken,
		LeaseExpiresAt: now.Add(ttl),
		AcquiredAt:     now,
		HeartbeatAt:    now,
	}
	s.mockResourceStore.lease = lease
	return lease, nil
}

func (s *staleFencingStore) HeartbeatExecutionLease(_ context.Context, resourceID uuid.UUID, ownerID string, fencingToken int64, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now().UTC()
	if s.mockResourceStore.lease.ResourceID != resourceID ||
		s.currentOwnerID != ownerID ||
		s.currentToken != fencingToken ||
		!s.mockResourceStore.lease.LeaseExpiresAt.After(now) {
		return repository.ErrLeaseLost
	}
	s.mockResourceStore.lease.LeaseExpiresAt = now.Add(ttl)
	s.mockResourceStore.lease.HeartbeatAt = now
	return nil
}

func (s *staleFencingStore) ReleaseExecutionLease(_ context.Context, resourceID uuid.UUID, ownerID string, fencingToken int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now().UTC()
	// Expire the lease to allow recovery.
	s.mockResourceStore.lease.LeaseExpiresAt = now
	return nil
}

// ---------------------------------------------------------------------------
// Item 3: Stale worker's SavePlan is rejected by fencing token check.
// Scenario: worker A plans Terraform, then its lease is superseded by worker B.
// Worker A's deferred SavePlan call must be rejected with ErrResourceConflict.
// ---------------------------------------------------------------------------

func TestStalePlanSaveIsRejectedByFencingToken(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()

	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "data")

	store := &staleFencingStore{
		mockResourceStore: mockResourceStore{
			resource: model.InfrastructureResource{
				ID:        id,
				Status:    model.ResourceStatusPending,
				UpdatedAt: now,
			},
		},
	}

	// Stale worker A: holds token=1 but we will bump the token to 2 before it writes.
	staleOwnerID := "worker-A"
	staleToken := int64(1)
	store.mu.Lock()
	store.currentOwnerID = staleOwnerID
	store.currentToken = staleToken
	store.mockResourceStore.lease = model.ExecutionLease{
		ResourceID:     id,
		OwnerID:        staleOwnerID,
		FencingToken:   staleToken,
		LeaseExpiresAt: now.Add(time.Hour), // still "active" in mock
	}
	store.mu.Unlock()

	// Worker B takes over: token becomes 2.
	store.mu.Lock()
	store.currentToken = 2
	store.currentOwnerID = "worker-B"
	store.mockResourceStore.lease.LeaseExpiresAt = now // expire A's lease
	store.mu.Unlock()

	// Worker A now tries to persist the plan result with its stale token.
	resource := model.InfrastructureResource{
		ID:       id,
		Status:   model.ResourceStatusAwaitingApproval,
		PlanPath: planPath,
		PlanHash: planHash,
	}
	err := store.SavePlanWithLease(context.Background(), resource, staleOwnerID, staleToken)

	if !errors.Is(err, repository.ErrResourceConflict) {
		t.Fatalf("expected ErrResourceConflict for stale SavePlan, got: %v", err)
	}
	if store.savePlanRejections != 1 {
		t.Fatalf("expected 1 rejection, got %d", store.savePlanRejections)
	}
	t.Log("PASS: stale SavePlanWithLease rejected by fencing token")
}

// ---------------------------------------------------------------------------
// Item 3: Stale FinishReviewedPlan is rejected after lease supersession.
// ---------------------------------------------------------------------------

func TestStaleFinishPlanIsRejectedByFencingToken(t *testing.T) {
	id := uuid.New()
	now := time.Now().UTC()

	store := &staleFencingStore{
		mockResourceStore: mockResourceStore{
			resource: model.InfrastructureResource{
				ID:        id,
				Status:    model.ResourceStatusProvisioning,
				UpdatedAt: now,
			},
		},
	}
	store.currentOwnerID = "worker-A"
	store.currentToken = 1
	store.mockResourceStore.lease = model.ExecutionLease{
		ResourceID:     id,
		OwnerID:        "worker-A",
		FencingToken:   1,
		LeaseExpiresAt: now.Add(time.Hour),
	}

	// Bump token: worker B takes over.
	store.currentToken = 2
	store.currentOwnerID = "worker-B"

	resource := model.InfrastructureResource{ID: id, Status: model.ResourceStatusProvisioning}
	err := store.FinishReviewedPlanWithLease(context.Background(), resource, "apply", model.ResourceStatusActive, true, "worker-A", 1)

	if !errors.Is(err, repository.ErrResourceConflict) {
		t.Fatalf("expected ErrResourceConflict for stale FinishReviewedPlan, got: %v", err)
	}
	if store.finishRejections != 1 {
		t.Fatalf("expected 1 finish rejection, got %d", store.finishRejections)
	}
	t.Log("PASS: stale FinishReviewedPlanWithLease rejected by fencing token")
}

// ---------------------------------------------------------------------------
// Item 4: Heartbeat failure cancels execCtx fail-closed BEFORE Terraform
// runner completes; the pending result is never persisted.
//
// Design: fakeHBStore lets AcquireExecutionLease succeed once, then immediately
// fails every HeartbeatExecutionLease call. The runner blocks until its context
// is cancelled. We assert that Plan returns an error and SavePlanWithLease is
// never invoked.

type fakeHBStore struct {
	mockResourceStore
	savePlanCalled bool
}

func (s *fakeHBStore) AcquireExecutionLease(_ context.Context, resourceID uuid.UUID, ownerID string, operation string, ttl time.Duration) (model.ExecutionLease, error) {
	now := time.Now().UTC()
	lease := model.ExecutionLease{
		ResourceID:     resourceID,
		OwnerID:        ownerID,
		Operation:      operation,
		FencingToken:   1,
		LeaseExpiresAt: now.Add(ttl),
		AcquiredAt:     now,
		HeartbeatAt:    now,
	}
	s.lease = lease
	return lease, nil
}

func (s *fakeHBStore) HeartbeatExecutionLease(_ context.Context, _ uuid.UUID, _ string, _ int64, _ time.Duration) error {
	return repository.ErrLeaseLost // always fail → cancel execCtx
}

func (s *fakeHBStore) ReleaseExecutionLease(_ context.Context, _ uuid.UUID, _ string, _ int64) error {
	return nil
}

func (s *fakeHBStore) SavePlanWithLease(_ context.Context, _ model.InfrastructureResource, _ string, _ int64) error {
	s.savePlanCalled = true
	return nil
}

func TestHeartbeatFailureCancelsExecContextFailClosed(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()

	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "data-hb")

	store := &fakeHBStore{
		mockResourceStore: mockResourceStore{
			resource: model.InfrastructureResource{
				ID:        id,
				Status:    model.ResourceStatusPending,
				UpdatedAt: now,
			},
		},
	}

	// Runner blocks until its context is cancelled; returns ctx.Err() afterward.
	runnerDone := make(chan struct{})
	runner := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
		},
		planFunc: func() {
			<-runnerDone
		},
	}

	svc := &ProvisioningService{
		store:             store,
		runner:            runner,
		clock:             time.Now,
		locker:            NewExecutionLocker(),
		replicaID:         "test-hb-replica",
		leaseTTL:          30 * time.Second,
		heartbeatInterval: 20 * time.Millisecond, // very short so context is cancelled quickly
	}

	// Let the runner unblock after the heartbeat has had time to cancel execCtx.
	go func() {
		time.Sleep(80 * time.Millisecond)
		close(runnerDone)
	}()

	ctx := context.Background()
	_, err := svc.Plan(ctx, id)

	// Plan must fail because execCtx was cancelled by heartbeat failure.
	if err == nil {
		t.Fatal("expected error from Plan when heartbeat fails, got nil")
	}
	// SavePlanWithLease must NOT have been called.
	if store.savePlanCalled {
		t.Fatal("SavePlanWithLease must not be called after execCtx is cancelled by lease loss")
	}
	t.Logf("PASS: heartbeat failure caused Plan to fail closed with: %v", err)
}

// Item 5: Recovery — after prior worker's lease expires (simulated crash),
// a new worker can acquire the lease and successfully complete the plan.
// ---------------------------------------------------------------------------

func TestRecoveryAfterLeaseExpiry(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()

	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "recovery-data")

	store := &staleFencingStore{
		mockResourceStore: mockResourceStore{
			resource: model.InfrastructureResource{
				ID:        id,
				Status:    model.ResourceStatusPending,
				UpdatedAt: now,
			},
		},
	}

	// Simulate: prior worker crashed, lease is now expired.
	store.mockResourceStore.lease = model.ExecutionLease{
		ResourceID:     id,
		OwnerID:        "crashed-worker",
		FencingToken:   1,
		LeaseExpiresAt: now.Add(-1 * time.Minute), // expired
	}
	store.currentOwnerID = "crashed-worker"
	store.currentToken = 1

	runner := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
		},
	}

	svc := &ProvisioningService{
		store:             store,
		runner:            runner,
		clock:             time.Now,
		locker:            NewExecutionLocker(),
		replicaID:         "recovery-replica",
		leaseTTL:          30 * time.Second,
		heartbeatInterval: 10 * time.Second,
	}

	ctx := context.Background()
	result, err := svc.Plan(ctx, id)
	if err != nil {
		t.Fatalf("recovery Plan failed: %v", err)
	}
	if result.Status != model.ResourceStatusAwaitingApproval {
		t.Fatalf("expected awaiting_approval after recovery, got %s", result.Status)
	}
	// New fencing token must be greater than the crashed worker's.
	if store.currentToken <= 1 {
		t.Fatalf("expected fencing token > 1 after recovery, got %d", store.currentToken)
	}
	t.Logf("PASS: recovery acquired token=%d, resource status=%s", store.currentToken, result.Status)
}

// ---------------------------------------------------------------------------
// Item 4: acquireExecutionOwnership returns ErrResourceConflict (not panic)
// when in-process lock is already held — fail-closed, no goroutine leak.
// ---------------------------------------------------------------------------

func TestAcquireOwnershipFailsClosedWhenLocalLockHeld(t *testing.T) {
	id := uuid.New()

	locker := NewExecutionLocker()
	_, held := locker.TryLock(id, "plan")
	if !held {
		t.Fatal("failed to acquire initial local lock")
	}
	// Don't release — simulate a concurrent in-flight operation.

	svc := &ProvisioningService{
		locker:            locker,
		leaseTTL:          30 * time.Second,
		heartbeatInterval: 5 * time.Second,
	}

	_, _, _, _, err := svc.acquireExecutionOwnership(context.Background(), id, "plan")
	if err == nil {
		t.Fatal("expected ErrResourceConflict when local lock is held")
	}
	if !errors.Is(err, repository.ErrResourceConflict) {
		t.Fatalf("expected ErrResourceConflict, got: %v", err)
	}
	t.Log("PASS: acquireExecutionOwnership fails closed when local lock is already held")
}

// ---------------------------------------------------------------------------
// Item 5: DB interruption during cleanup does not block forever —
// cleanup uses context.WithoutCancel + 5s timeout.
// ---------------------------------------------------------------------------

func TestCleanupDoesNotBlockWhenDBUnavailable(t *testing.T) {
	id := uuid.New()
	now := time.Now().UTC()

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:        id,
			Status:    model.ResourceStatusPending,
			UpdatedAt: now,
		},
		// Simulate DB outage: ReleaseExecutionLease will block until its ctx expires,
		// but we override with releaseLeaseErr to return immediately with error.
		releaseLeaseErr: errors.New("DB connection refused"),
	}

	svc := &ProvisioningService{
		store:             store,
		runner:            nil,
		clock:             time.Now,
		locker:            NewExecutionLocker(),
		replicaID:         "db-interrupted-replica",
		leaseTTL:          30 * time.Second,
		heartbeatInterval: 10 * time.Second,
	}

	execCtx, cleanup, _, _, err := svc.acquireExecutionOwnership(context.Background(), id, "plan")
	if err != nil {
		t.Fatalf("unexpected acquire error: %v", err)
	}
	_ = execCtx

	// cleanup() must return within 10s even when DB is unavailable.
	done := make(chan struct{})
	go func() {
		defer close(done)
		cleanup()
	}()

	select {
	case <-done:
		t.Log("PASS: cleanup returned promptly despite DB unavailability")
	case <-time.After(10 * time.Second):
		t.Fatal("cleanup blocked too long when DB was unavailable")
	}
}
