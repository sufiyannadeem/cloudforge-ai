package service

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"
)

type mockProvisionRunner struct {
	planResult      terraform.PlanResult
	planErr         error
	applyErr        error
	planCalls       int
	applyCalls      int
	lastApplyRes    model.InfrastructureResource
	destroyPlanRes  terraform.PlanResult
	destroyPlanErr  error
	destroyApplyErr error
}

func (m *mockProvisionRunner) Plan(ctx context.Context, resource model.InfrastructureResource) (terraform.PlanResult, error) {
	m.planCalls++
	return m.planResult, m.planErr
}

func (m *mockProvisionRunner) Apply(ctx context.Context, resource model.InfrastructureResource) error {
	m.applyCalls++
	m.lastApplyRes = resource
	return m.applyErr
}

func (m *mockProvisionRunner) PlanDestroy(ctx context.Context, resource model.InfrastructureResource) (terraform.PlanResult, error) {
	return m.destroyPlanRes, m.destroyPlanErr
}

func (m *mockProvisionRunner) ApplyDestroy(ctx context.Context, resource model.InfrastructureResource) error {
	return m.destroyApplyErr
}

func writePlanFile(t *testing.T, dir, filename, content string) (string, string) {
	t.Helper()
	path := filepath.Join(dir, filename)
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write plan file: %v", err)
	}
	hasher := sha256.New()
	hasher.Write([]byte(content))
	hash := fmt.Sprintf("%x", hasher.Sum(nil))
	return path, hash
}

func TestPlanSuccessStoresPlanMetadataAndSummary(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Date(2026, 10, 27, 10, 0, 0, 0, time.UTC)

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:           id,
			Name:         "Dev VPC",
			ResourceType: "aws_vpc",
			Provider:     model.ProviderAWS,
			Region:       "eu-west-1",
			Environment:  "dev",
			Status:       model.ResourceStatusPending,
		},
	}

	planPath, planHash := writePlanFile(t, dir, "cloudforge.tfplan", "mock-plan-bytes")
	runner := &mockProvisionRunner{
		planResult: terraform.PlanResult{
			WorkspaceDirectory: dir,
			PlanPath:           planPath,
			PlanHash:           planHash,
			PlanCreatedAt:      now,
			PlanSummary:        "Terraform plan: 1 to add, 0 to change, 0 to destroy",
		},
	}

	svc := NewProvisioningService(store, runner)
	svc.clock = func() time.Time { return now }

	result, err := svc.Plan(context.Background(), id)
	if err != nil {
		t.Fatalf("unexpected plan error: %v", err)
	}

	if runner.planCalls != 1 {
		t.Fatalf("expected 1 runner plan call, got %d", runner.planCalls)
	}
	if result.Status != model.ResourceStatusAwaitingApproval {
		t.Fatalf("expected status awaiting_approval, got %s", result.Status)
	}
	if result.PlanHash != planHash {
		t.Fatalf("expected plan hash %q, got %q", planHash, result.PlanHash)
	}
	if result.PlanSummary != "Terraform plan: 1 to add, 0 to change, 0 to destroy" {
		t.Fatalf("expected plan summary, got %q", result.PlanSummary)
	}
	if result.ApprovalExpiresAt == nil || !result.ApprovalExpiresAt.Equal(now.Add(30*time.Minute)) {
		t.Fatalf("expected 30m approval expiration, got %v", result.ApprovalExpiresAt)
	}
}

func TestPlanRejectsInvalidProvisioningState(t *testing.T) {
	invalidStatuses := []model.ResourceStatus{
		model.ResourceStatusActive,
		model.ResourceStatusProvisioning,
		model.ResourceStatusDestroying,
		model.ResourceStatusAwaitingApproval,
		model.ResourceStatusAwaitingDestroyApproval,
		model.ResourceStatusDestroyed,
	}

	for _, st := range invalidStatuses {
		t.Run(string(st), func(t *testing.T) {
			id := uuid.New()
			store := &mockResourceStore{
				resource: model.InfrastructureResource{
					ID:     id,
					Status: st,
				},
			}
			runner := &mockProvisionRunner{}
			svc := NewProvisioningService(store, runner)

			_, err := svc.Plan(context.Background(), id)
			if !errors.Is(err, ErrInvalidProvisioningState) {
				t.Fatalf("expected ErrInvalidProvisioningState for %s, got %v", st, err)
			}
			if runner.planCalls != 0 {
				t.Fatalf("runner should not be called for status %s", st)
			}
		})
	}
}

func TestPlanFailureTransitionsToFailed(t *testing.T) {
	id := uuid.New()
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:     id,
			Status: model.ResourceStatusPending,
		},
	}
	runner := &mockProvisionRunner{
		planErr: errors.New("simulated terraform plan failure"),
	}

	svc := NewProvisioningService(store, runner)

	_, err := svc.Plan(context.Background(), id)
	if err == nil || !errors.Is(err, runner.planErr) {
		t.Fatalf("expected plan error, got %v", err)
	}

	if store.resource.Status != model.ResourceStatusFailed {
		t.Fatalf("expected store resource to transition to failed, got %s", store.resource.Status)
	}
}

func TestApplySuccessTransitionsToActive(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Date(2026, 10, 27, 10, 0, 0, 0, time.UTC)
	expires := now.Add(30 * time.Minute)

	planPath, planHash := writePlanFile(t, dir, "cloudforge.tfplan", "valid-plan-data")

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:                id,
			Name:              "Dev EC2",
			ResourceType:      "aws_ec2",
			Status:            model.ResourceStatusAwaitingApproval,
			PlanPath:          planPath,
			PlanHash:          planHash,
			PlanCreatedAt:     &now,
			ApprovalExpiresAt: &expires,
		},
	}

	runner := &mockProvisionRunner{}
	svc := NewProvisioningService(store, runner)
	svc.clock = func() time.Time { return now.Add(5 * time.Minute) }

	result, err := svc.Apply(context.Background(), id, planHash)
	if err != nil {
		t.Fatalf("unexpected apply error: %v", err)
	}

	if runner.applyCalls != 1 {
		t.Fatalf("expected 1 runner apply call, got %d", runner.applyCalls)
	}
	if result.Status != model.ResourceStatusActive {
		t.Fatalf("expected active status, got %s", result.Status)
	}
}

func TestApplyRejectsExpiredApproval(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	created := time.Date(2026, 10, 27, 10, 0, 0, 0, time.UTC)
	expires := created.Add(30 * time.Minute)

	planPath, planHash := writePlanFile(t, dir, "cloudforge.tfplan", "data")

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:                id,
			Status:            model.ResourceStatusAwaitingApproval,
			PlanPath:          planPath,
			PlanHash:          planHash,
			PlanCreatedAt:     &created,
			ApprovalExpiresAt: &expires,
		},
	}

	runner := &mockProvisionRunner{}
	svc := NewProvisioningService(store, runner)
	// Clock is 31 minutes after creation (expired)
	svc.clock = func() time.Time { return created.Add(31 * time.Minute) }

	_, err := svc.Apply(context.Background(), id, planHash)
	if !errors.Is(err, ErrApprovalExpired) {
		t.Fatalf("expected ErrApprovalExpired, got %v", err)
	}
	if runner.applyCalls != 0 {
		t.Fatal("apply must not be invoked when approval is expired")
	}
	if store.resource.Status != model.ResourceStatusFailed {
		t.Fatalf("expected status failed on expired approval, got %s", store.resource.Status)
	}
}

func TestApplyRejectsHashMismatch(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Date(2026, 10, 27, 10, 0, 0, 0, time.UTC)
	expires := now.Add(30 * time.Minute)

	planPath, planHash := writePlanFile(t, dir, "cloudforge.tfplan", "data")

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:                id,
			Status:            model.ResourceStatusAwaitingApproval,
			PlanPath:          planPath,
			PlanHash:          planHash,
			ApprovalExpiresAt: &expires,
		},
	}

	runner := &mockProvisionRunner{}
	svc := NewProvisioningService(store, runner)
	svc.clock = func() time.Time { return now }

	_, err := svc.Apply(context.Background(), id, "wrong-hash")
	if !errors.Is(err, ErrPlanHashMismatch) {
		t.Fatalf("expected ErrPlanHashMismatch, got %v", err)
	}
	if runner.applyCalls != 0 {
		t.Fatal("apply must not be called when hash mismatches")
	}
}

func TestApplyRejectsTamperedPlanFile(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Date(2026, 10, 27, 10, 0, 0, 0, time.UTC)
	expires := now.Add(30 * time.Minute)

	planPath, originalHash := writePlanFile(t, dir, "cloudforge.tfplan", "original-plan")

	// Tamper with the plan file on disk
	if err := os.WriteFile(planPath, []byte("tampered-plan"), 0o600); err != nil {
		t.Fatal(err)
	}

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:                id,
			Status:            model.ResourceStatusAwaitingApproval,
			PlanPath:          planPath,
			PlanHash:          originalHash,
			ApprovalExpiresAt: &expires,
		},
	}

	runner := &mockProvisionRunner{}
	svc := NewProvisioningService(store, runner)
	svc.clock = func() time.Time { return now }

	_, err := svc.Apply(context.Background(), id, originalHash)
	if !errors.Is(err, ErrPlanHashMismatch) {
		t.Fatalf("expected ErrPlanHashMismatch for tampered plan, got %v", err)
	}
	if runner.applyCalls != 0 {
		t.Fatal("apply must not be called when plan file was tampered with")
	}
	if store.resource.Status != model.ResourceStatusFailed {
		t.Fatalf("expected status failed after tampered plan, got %s", store.resource.Status)
	}
}

func TestApplyFailureTransitionsToFailed(t *testing.T) {
	id := uuid.New()
	dir := t.TempDir()
	now := time.Date(2026, 10, 27, 10, 0, 0, 0, time.UTC)
	expires := now.Add(30 * time.Minute)

	planPath, planHash := writePlanFile(t, dir, "cloudforge.tfplan", "plan-data")

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:                id,
			Status:            model.ResourceStatusAwaitingApproval,
			PlanPath:          planPath,
			PlanHash:          planHash,
			ApprovalExpiresAt: &expires,
		},
	}

	runner := &mockProvisionRunner{
		applyErr: errors.New("simulated terraform apply network timeout"),
	}

	svc := NewProvisioningService(store, runner)
	svc.clock = func() time.Time { return now }

	_, err := svc.Apply(context.Background(), id, planHash)
	if err == nil || !errors.Is(err, runner.applyErr) {
		t.Fatalf("expected apply error, got %v", err)
	}

	if store.resource.Status != model.ResourceStatusFailed {
		t.Fatalf("expected resource status failed after apply error, got %s", store.resource.Status)
	}
}

func TestGetPlanReturnsPlanDetails(t *testing.T) {
	id := uuid.New()
	now := time.Date(2026, 10, 27, 10, 0, 0, 0, time.UTC)
	expires := now.Add(30 * time.Minute)

	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:                id,
			Name:              "Production RDS",
			ResourceType:      "aws_rds",
			Provider:          model.ProviderAWS,
			Region:            "eu-west-1",
			Environment:       "prod",
			Status:            model.ResourceStatusAwaitingApproval,
			PlanHash:          "hash-rds-123",
			PlanSummary:       "Terraform plan: 1 to add",
			PlanCreatedAt:     &now,
			ApprovalExpiresAt: &expires,
			Configuration: map[string]any{
				"engine": "postgres",
			},
		},
	}

	svc := NewProvisioningService(store, &mockProvisionRunner{})
	svc.clock = func() time.Time { return now.Add(10 * time.Minute) }

	details, err := svc.GetPlan(context.Background(), id)
	if err != nil {
		t.Fatalf("unexpected GetPlan error: %v", err)
	}

	if details.ResourceID != id {
		t.Fatalf("expected resource id %s, got %s", id, details.ResourceID)
	}
	if details.PlanHash != "hash-rds-123" {
		t.Fatalf("expected plan hash %q, got %q", "hash-rds-123", details.PlanHash)
	}
	if details.IsExpired {
		t.Fatal("plan should not be expired within 10 minutes of 30m window")
	}
	if details.PlanSummary != "Terraform plan: 1 to add" {
		t.Fatalf("expected plan summary, got %q", details.PlanSummary)
	}
}
