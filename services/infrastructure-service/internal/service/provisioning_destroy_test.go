package service

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"
)

type fakeRunner struct {
	planDestroyResult terraform.PlanResult
	planDestroyErr    error
	applyDestroyErr   error
	planDestroyCalls  int
	applyDestroyCalls int
}

func (f *fakeRunner) Plan(context.Context, model.InfrastructureResource) (terraform.PlanResult, error) {
	return terraform.PlanResult{}, errors.New("unexpected Plan call")
}

func (f *fakeRunner) Apply(context.Context, model.InfrastructureResource) error {
	return errors.New("unexpected Apply call")
}

func (f *fakeRunner) PlanDestroy(context.Context, model.InfrastructureResource) (terraform.PlanResult, error) {
	f.planDestroyCalls++
	return f.planDestroyResult, f.planDestroyErr
}

func (f *fakeRunner) ApplyDestroy(context.Context, model.InfrastructureResource) error {
	f.applyDestroyCalls++
	return f.applyDestroyErr
}

var destroyNow = time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

func newDestroyService(store *mockResourceStore, runner *fakeRunner) *ProvisioningService {
	svc := NewProvisioningService(store, runner)
	svc.clock = func() time.Time { return destroyNow }
	return svc
}

func TestPlanDestroyStoresHashedPlanAndOpensApprovalWindow(t *testing.T) {
	id := uuid.New()
	store := &mockResourceStore{resource: model.InfrastructureResource{ID: id, Status: model.ResourceStatusActive}}
	runner := &fakeRunner{planDestroyResult: terraform.PlanResult{
		PlanPath: "/ws/destroy.tfplan", PlanHash: "hash1", PlanCreatedAt: destroyNow,
	}}

	got, err := newDestroyService(store, runner).PlanDestroy(context.Background(), id)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if got.Status != model.ResourceStatusAwaitingDestroyApproval {
		t.Fatalf("unexpected status %s", got.Status)
	}
	if got.DestroyPlanHash != "hash1" || got.DestroyPlanPath != "/ws/destroy.tfplan" {
		t.Fatalf("destroy plan not recorded: %+v", got)
	}
	if got.ApprovalExpiresAt == nil || !got.ApprovalExpiresAt.Equal(destroyNow.Add(30*time.Minute)) {
		t.Fatalf("expected 30 minute approval window, got %v", got.ApprovalExpiresAt)
	}
	if store.resource.Status != model.ResourceStatusAwaitingDestroyApproval {
		t.Fatalf("status not persisted: %s", store.resource.Status)
	}
}

func TestPlanDestroyRejectsNonActiveResources(t *testing.T) {
	for _, status := range []model.ResourceStatus{
		model.ResourceStatusPending, model.ResourceStatusAwaitingApproval,
		model.ResourceStatusProvisioning, model.ResourceStatusDestroyed, model.ResourceStatusFailed,
	} {
		id := uuid.New()
		store := &mockResourceStore{resource: model.InfrastructureResource{ID: id, Status: status}}
		runner := &fakeRunner{}

		_, err := newDestroyService(store, runner).PlanDestroy(context.Background(), id)
		if !errors.Is(err, ErrInvalidProvisioningState) {
			t.Fatalf("status %s: expected ErrInvalidProvisioningState, got %v", status, err)
		}
		if runner.planDestroyCalls != 0 {
			t.Fatalf("status %s: runner must not be invoked", status)
		}
	}
}

func TestPlanDestroyFailureRestoresActive(t *testing.T) {
	id := uuid.New()
	store := &mockResourceStore{resource: model.InfrastructureResource{ID: id, Status: model.ResourceStatusActive}}
	runner := &fakeRunner{planDestroyErr: errors.New("boom")}

	if _, err := newDestroyService(store, runner).PlanDestroy(context.Background(), id); err == nil {
		t.Fatal("expected error")
	}
	if store.resource.Status != model.ResourceStatusActive {
		t.Fatalf("expected active after failed destroy plan, got %s", store.resource.Status)
	}
}

func awaitingDestroy(t *testing.T, expires time.Time) (*mockResourceStore, uuid.UUID, string) {
	t.Helper()

	path := filepath.Join(t.TempDir(), "destroy.tfplan")
	if err := os.WriteFile(path, []byte("destroy-plan"), 0o600); err != nil {
		t.Fatal(err)
	}
	hash, err := hashFile(path)
	if err != nil {
		t.Fatal(err)
	}

	id := uuid.New()
	return &mockResourceStore{resource: model.InfrastructureResource{
		ID: id, Status: model.ResourceStatusAwaitingDestroyApproval,
		DestroyPlanPath: path, DestroyPlanHash: hash, ApprovalExpiresAt: &expires,
	}}, id, hash
}

func TestApplyDestroySuccess(t *testing.T) {
	store, id, hash := awaitingDestroy(t, destroyNow.Add(10*time.Minute))
	runner := &fakeRunner{}

	got, err := newDestroyService(store, runner).ApplyDestroy(context.Background(), id, hash)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Status != model.ResourceStatusDestroyed || store.resource.Status != model.ResourceStatusDestroyed {
		t.Fatalf("expected destroyed, got %s / %s", got.Status, store.resource.Status)
	}
	if runner.applyDestroyCalls != 1 {
		t.Fatalf("expected one runner call, got %d", runner.applyDestroyCalls)
	}
}

func TestApplyDestroyExpiredApprovalRevertsToActive(t *testing.T) {
	store, id, hash := awaitingDestroy(t, destroyNow.Add(-time.Second))
	runner := &fakeRunner{}

	_, err := newDestroyService(store, runner).ApplyDestroy(context.Background(), id, hash)
	if !errors.Is(err, ErrApprovalExpired) {
		t.Fatalf("expected ErrApprovalExpired, got %v", err)
	}
	if runner.applyDestroyCalls != 0 {
		t.Fatal("runner must not run with an expired approval")
	}
	if store.resource.Status != model.ResourceStatusActive {
		t.Fatalf("expected active, got %s", store.resource.Status)
	}
}

func TestApplyDestroyRejectsWrongOrMissingHash(t *testing.T) {
	for _, supplied := range []string{"", "deadbeef"} {
		store, id, _ := awaitingDestroy(t, destroyNow.Add(time.Minute))
		runner := &fakeRunner{}

		_, err := newDestroyService(store, runner).ApplyDestroy(context.Background(), id, supplied)
		if !errors.Is(err, ErrPlanHashMismatch) {
			t.Fatalf("hash %q: expected ErrPlanHashMismatch, got %v", supplied, err)
		}
		if runner.applyDestroyCalls != 0 {
			t.Fatal("runner must not run without a matching approval hash")
		}
	}
}

func TestApplyDestroyDetectsTamperedPlanFile(t *testing.T) {
	store, id, hash := awaitingDestroy(t, destroyNow.Add(time.Minute))
	if err := os.WriteFile(store.resource.DestroyPlanPath, []byte("tampered"), 0o600); err != nil {
		t.Fatal(err)
	}
	runner := &fakeRunner{}

	_, err := newDestroyService(store, runner).ApplyDestroy(context.Background(), id, hash)
	if !errors.Is(err, ErrPlanHashMismatch) {
		t.Fatalf("expected ErrPlanHashMismatch, got %v", err)
	}
	if runner.applyDestroyCalls != 0 || store.resource.Status != model.ResourceStatusActive {
		t.Fatalf("tampered plan must not run (calls=%d status=%s)", runner.applyDestroyCalls, store.resource.Status)
	}
}

func TestApplyDestroyRequiresAwaitingDestroyApproval(t *testing.T) {
	id := uuid.New()
	store := &mockResourceStore{resource: model.InfrastructureResource{ID: id, Status: model.ResourceStatusActive}}

	_, err := newDestroyService(store, &fakeRunner{}).ApplyDestroy(context.Background(), id, "x")
	if !errors.Is(err, ErrInvalidProvisioningState) {
		t.Fatalf("expected ErrInvalidProvisioningState, got %v", err)
	}
}

func TestApplyDestroyRunnerFailureRestoresActive(t *testing.T) {
	store, id, hash := awaitingDestroy(t, destroyNow.Add(time.Minute))
	runner := &fakeRunner{applyDestroyErr: errors.New("terraform destroy failed")}

	if _, err := newDestroyService(store, runner).ApplyDestroy(context.Background(), id, hash); err == nil {
		t.Fatal("expected error")
	}
	if store.resource.Status != model.ResourceStatusActive {
		t.Fatalf("expected active after failed destroy, got %s", store.resource.Status)
	}
}
