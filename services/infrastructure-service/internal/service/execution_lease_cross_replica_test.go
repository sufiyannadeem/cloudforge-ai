package service

import (
	"context"
	"errors"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"
)

func TestCrossReplicaPlanMutualExclusion(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:        id,
			Status:    model.ResourceStatusPending,
			UpdatedAt: now,
		},
	}
	plan1Started := make(chan struct{})
	plan1Blocker := make(chan struct{})
	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "plan-bytes")

	runner1 := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
		},
		planFunc: func() {
			close(plan1Started)
			<-plan1Blocker
		},
	}
	runner2 := &mockProvisionRunner{}

	// Two separate service instances representing two different pods
	replica1 := NewProvisioningService(store, runner1)
	replica1.replicaID = "pod-replica-1"

	replica2 := NewProvisioningService(store, runner2)
	replica2.replicaID = "pod-replica-2"

	firstErrCh := make(chan error, 1)
	go func() {
		_, err := replica1.Plan(context.Background(), id)
		firstErrCh <- err
	}()

	<-plan1Started

	// Replica 2 attempts Plan on the same resource concurrently
	_, err := replica2.Plan(context.Background(), id)
	if !errors.Is(err, repository.ErrResourceConflict) {
		t.Fatalf("expected ErrResourceConflict on replica 2, got %v", err)
	}

	close(plan1Blocker)
	if err := <-firstErrCh; err != nil {
		t.Fatalf("expected replica 1 plan to succeed, got %v", err)
	}
}

func TestCrossReplicaPlanRejectsWhileApplyActive(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()
	expiry := now.Add(time.Hour)
	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "plan-bytes")

	store := &approvalRequiredStore{
		hasApproval: true,
		mockResourceStore: &mockResourceStore{
			resource: model.InfrastructureResource{
				ID:                id,
				Status:            model.ResourceStatusAwaitingApproval,
				PlanPath:          planPath,
				PlanHash:          planHash,
				ApprovalExpiresAt: &expiry,
				UpdatedAt:         now,
			},
		},
	}

	applyStarted := make(chan struct{})
	applyBlocker := make(chan struct{})
	runner1 := &mockProvisionRunner{
		applyFunc: func() {
			close(applyStarted)
			<-applyBlocker
		},
	}
	runner2 := &mockProvisionRunner{}

	replica1 := NewProvisioningService(store, runner1)
	replica1.replicaID = "pod-replica-1"

	replica2 := NewProvisioningService(store, runner2)
	replica2.replicaID = "pod-replica-2"

	applyErrCh := make(chan error, 1)
	go func() {
		_, err := replica1.Apply(context.Background(), id, planHash)
		applyErrCh <- err
	}()

	<-applyStarted

	// Replica 2 attempts Plan while Replica 1 is applying
	_, err := replica2.Plan(context.Background(), id)
	if !errors.Is(err, repository.ErrResourceConflict) {
		t.Fatalf("expected ErrResourceConflict on replica 2 during apply, got %v", err)
	}

	close(applyBlocker)
	if err := <-applyErrCh; err != nil {
		t.Fatalf("expected replica 1 apply to succeed, got %v", err)
	}
}

func TestCrossReplicaPlanningRetryBlockedWhileActive(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:        id,
			Status:    model.ResourceStatusPlanning,
			UpdatedAt: now,
		},
	}

	planStarted := make(chan struct{})
	planBlocker := make(chan struct{})
	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "retry-bytes")

	runner1 := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
		},
		planFunc: func() {
			close(planStarted)
			<-planBlocker
		},
	}
	runner2 := &mockProvisionRunner{}

	replica1 := NewProvisioningService(store, runner1)
	replica1.replicaID = "pod-replica-1"

	replica2 := NewProvisioningService(store, runner2)
	replica2.replicaID = "pod-replica-2"

	firstErrCh := make(chan error, 1)
	go func() {
		_, err := replica1.Plan(context.Background(), id)
		firstErrCh <- err
	}()

	<-planStarted

	// While replica 1 is actively planning, replica 2 receives a "Retry Plan" request
	_, err := replica2.Plan(context.Background(), id)
	if !errors.Is(err, repository.ErrResourceConflict) {
		t.Fatalf("expected planning->planning retry to be blocked with ErrResourceConflict while active, got %v", err)
	}

	close(planBlocker)
	if err := <-firstErrCh; err != nil {
		t.Fatalf("expected replica 1 plan to succeed, got %v", err)
	}
}

func TestCrossReplicaStaleExecutionRecoveryAfterLeaseExpiry(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:        id,
			Status:    model.ResourceStatusPlanning,
			UpdatedAt: now,
		},
	}

	// Pre-populate an expired lease held by a crashed replica
	store.lease = model.ExecutionLease{
		ResourceID:     id,
		OwnerID:        "crashed-replica-dead:token",
		Operation:      "plan",
		FencingToken:   1,
		LeaseExpiresAt: now.Add(-10 * time.Second), // expired
		AcquiredAt:     now.Add(-60 * time.Second),
		HeartbeatAt:    now.Add(-40 * time.Second),
	}

	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "recovered-plan")
	runner2 := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
		},
	}

	replica2 := NewProvisioningService(store, runner2)
	replica2.replicaID = "pod-replica-2"

	// Replica 2 safely acquires the expired lease and recovers the execution
	res, err := replica2.Plan(context.Background(), id)
	if err != nil {
		t.Fatalf("expected replica 2 to successfully recover stale execution: %v", err)
	}
	if res.Status != model.ResourceStatusAwaitingApproval {
		t.Fatalf("expected status awaiting_approval after recovery, got %s", res.Status)
	}
}

func TestFencingTokenHeartbeatFailureCancelsExecutionContext(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:        id,
			Status:    model.ResourceStatusPending,
			UpdatedAt: now,
		},
	}

	contextCanceled := make(chan struct{})
	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "plan-bytes")
	runner := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
		},
	}

	svc := NewProvisioningService(store, runner)
	svc.replicaID = "fenced-pod"
	svc.leaseTTL = 100 * time.Millisecond
	svc.heartbeatInterval = 20 * time.Millisecond

	// Hook into Plan: when runner is called, simulate heartbeat failure (lease lost)
	runner.planFunc = func() {
		store.heartbeatLeaseErr = repository.ErrLeaseLost
		time.Sleep(50 * time.Millisecond)
	}

	var planErr error
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		_, planErr = svc.Plan(context.Background(), id)
	}()

	// Wait for plan to exit
	wg.Wait()
	_ = contextCanceled

	if planErr == nil {
		t.Fatal("expected error due to canceled context / lease lost, got nil")
	}
}

func TestPostgreSQLCrossReplicaPlanMutualExclusionAndRecovery(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL not set; skipping PostgreSQL cross-replica test")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)

	schema := pgx.Identifier{"cross_replica_" + uuid.NewString()}.Sanitize()
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("connect to database: %v", err)
	}
	t.Cleanup(adminPool.Close)

	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatalf("create schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schema+" CASCADE")
	})

	config := adminPool.Config()
	config.ConnConfig.RuntimeParams["search_path"] = schema
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("create pool: %v", err)
	}
	t.Cleanup(pool.Close)

	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatalf("run migrations: %v", err)
	}

	repo := repository.NewResourceRepository(pool)
	resID := uuid.New()
	dir := t.TempDir()
	now := time.Now().UTC()

	resource := model.InfrastructureResource{
		ID:                 resID,
		Name:               "Distributed Test VPC",
		ResourceType:       "aws_vpc",
		Provider:           model.ProviderAWS,
		Region:             "eu-west-1",
		Environment:        "dev",
		Status:             model.ResourceStatusPending,
		TerraformDirectory: dir,
		CreatedAt:          now,
		UpdatedAt:          now,
	}
	if err := repo.Create(ctx, resource); err != nil {
		t.Fatalf("create resource: %v", err)
	}

	planPath, planHash := writePlanFile(t, dir, "plan.tfplan", "pg-plan-bytes")
	plan1Started := make(chan struct{})
	plan1Blocker := make(chan struct{})

	runner1 := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
			PlanSummary:        "1 to add",
		},
		planFunc: func() {
			close(plan1Started)
			<-plan1Blocker
		},
	}
	runner2 := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
			PlanSummary:        "1 to add",
		},
	}

	replica1 := NewProvisioningService(repo, runner1)
	replica1.replicaID = "pod-replica-1"

	replica2 := NewProvisioningService(repo, runner2)
	replica2.replicaID = "pod-replica-2"

	// 1. Replica 1 starts Plan
	firstErrCh := make(chan error, 1)
	go func() {
		_, err := replica1.Plan(context.Background(), resID)
		firstErrCh <- err
	}()

	<-plan1Started

	// 2. Replica 2 calls Plan concurrently on the SAME PostgreSQL database
	_, err = replica2.Plan(context.Background(), resID)
	if !errors.Is(err, repository.ErrResourceConflict) {
		t.Fatalf("expected PostgreSQL ErrResourceConflict on replica 2 while replica 1 holds lease, got %v", err)
	}

	// 3. Unblock Replica 1 and let it finish
	close(plan1Blocker)
	if err := <-firstErrCh; err != nil {
		t.Fatalf("expected replica 1 to succeed, got %v", err)
	}

	// 4. Verify lease row exists in Postgres with valid metadata
	lease, err := repo.GetExecutionLease(ctx, resID)
	if err != nil {
		t.Fatalf("get execution lease: %v", err)
	}
	if lease.FencingToken != 1 {
		t.Fatalf("expected fencing token 1, got %d", lease.FencingToken)
	}
}
