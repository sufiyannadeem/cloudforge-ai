package service

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
)

type mockResourceStore struct {
	createCalled      bool
	created           model.InfrastructureResource
	resource          model.InfrastructureResource
	updated           model.InfrastructureResource
	updateCalled      bool
	transitionErr     error
	claimPlanErr      error
	lease             model.ExecutionLease
	acquireLeaseErr   error
	heartbeatLeaseErr error
	releaseLeaseErr   error
}

func (m *mockResourceStore) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	_ = ctx
	if m.resource.ID == id {
		return m.resource, nil
	}
	return model.InfrastructureResource{}, repository.ErrResourceNotFound
}

func (m *mockResourceStore) Create(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	m.createCalled = true
	m.created = resource
	return nil
}

func (m *mockResourceStore) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.InfrastructureResource, error) {
	return []model.InfrastructureResource{}, nil
}

func (m *mockResourceStore) Update(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	_ = ctx
	m.updateCalled = true
	m.updated = resource
	m.resource = resource
	return nil
}

func (m *mockResourceStore) TransitionStatus(
	ctx context.Context,
	id uuid.UUID,
	from []model.ResourceStatus,
	to model.ResourceStatus,
) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if m.transitionErr != nil {
		return m.transitionErr
	}
	if m.resource.ID != id {
		return repository.ErrResourceNotFound
	}
	allowed := false
	for _, status := range from {
		if m.resource.Status == status {
			allowed = true
			break
		}
	}
	if !allowed {
		return repository.ErrResourceConflict
	}
	m.resource.Status = to
	m.resource.UpdatedAt = m.resource.UpdatedAt.Add(time.Microsecond)
	m.updated = m.resource
	m.updateCalled = true
	return nil
}

func (m *mockResourceStore) ClaimPlan(ctx context.Context, resource model.InfrastructureResource) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if m.claimPlanErr != nil {
		return m.claimPlanErr
	}
	if m.resource.ID != resource.ID {
		return repository.ErrResourceNotFound
	}
	if !m.resource.UpdatedAt.IsZero() && !resource.UpdatedAt.IsZero() && !m.resource.UpdatedAt.Equal(resource.UpdatedAt) {
		return repository.ErrResourceConflict
	}
	allowed := false
	for _, st := range []model.ResourceStatus{model.ResourceStatusPending, model.ResourceStatusFailed, model.ResourceStatusPlanning, model.ResourceStatusActive} {
		if m.resource.Status == st {
			allowed = true
			break
		}
	}
	if !allowed {
		return repository.ErrResourceConflict
	}
	m.resource.Status = model.ResourceStatusPlanning
	m.resource.UpdatedAt = m.resource.UpdatedAt.Add(time.Microsecond)
	m.updated = m.resource
	m.updateCalled = true
	return nil
}

func (m *mockResourceStore) SavePlan(ctx context.Context, resource model.InfrastructureResource) error {
	_ = ctx
	if m.resource.ID != resource.ID {
		return repository.ErrResourceNotFound
	}
	if m.resource.Status != model.ResourceStatusPlanning {
		return repository.ErrResourceConflict
	}
	m.resource = resource
	m.updated = resource
	m.updateCalled = true
	return nil
}

func (m *mockResourceStore) SaveDestroyPlan(ctx context.Context, resource model.InfrastructureResource) error {
	_ = ctx
	if m.resource.ID != resource.ID {
		return repository.ErrResourceNotFound
	}
	if m.resource.Status != model.ResourceStatusPlanning {
		return repository.ErrResourceConflict
	}
	m.resource = resource
	m.updated = resource
	m.updateCalled = true
	return nil
}

func (m *mockResourceStore) UpdateEditable(ctx context.Context, id uuid.UUID, input model.UpdateResourceInput, expectedStatus model.ResourceStatus) error {
	_ = ctx
	if m.resource.ID != id {
		return repository.ErrResourceNotFound
	}
	if m.resource.Status != expectedStatus {
		return repository.ErrResourceConflict
	}
	if input.Name != nil {
		m.resource.Name = *input.Name
	}
	if input.Description != nil {
		m.resource.Description = *input.Description
	}
	if input.Region != nil {
		m.resource.Region = *input.Region
	}
	if input.Environment != nil {
		m.resource.Environment = *input.Environment
	}
	if input.TerraformDirectory != nil {
		m.resource.TerraformDirectory = *input.TerraformDirectory
	}
	if input.Configuration != nil {
		m.resource.Configuration = input.Configuration
	}
	m.resource.UpdatedAt = time.Now().UTC()
	m.updated = m.resource
	m.updateCalled = true
	return nil
}

func (m *mockResourceStore) DeleteIfStatusAllowed(
	ctx context.Context,
	id uuid.UUID,
) error {
	return nil
}

func (m *mockResourceStore) AcquireExecutionLease(ctx context.Context, resourceID uuid.UUID, ownerID string, operation string, ttl time.Duration) (model.ExecutionLease, error) {
	if err := ctx.Err(); err != nil {
		return model.ExecutionLease{}, err
	}
	if m.acquireLeaseErr != nil {
		return model.ExecutionLease{}, m.acquireLeaseErr
	}
	now := time.Now().UTC()
	if m.lease.ResourceID == resourceID && m.lease.LeaseExpiresAt.After(now) {
		return model.ExecutionLease{}, repository.ErrResourceConflict
	}
	m.lease = model.ExecutionLease{
		ResourceID:     resourceID,
		OwnerID:        ownerID,
		Operation:      operation,
		FencingToken:   m.lease.FencingToken + 1,
		LeaseExpiresAt: now.Add(ttl),
		AcquiredAt:     now,
		HeartbeatAt:    now,
	}
	return m.lease, nil
}

func (m *mockResourceStore) HeartbeatExecutionLease(ctx context.Context, resourceID uuid.UUID, ownerID string, fencingToken int64, ttl time.Duration) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if m.heartbeatLeaseErr != nil {
		return m.heartbeatLeaseErr
	}
	now := time.Now().UTC()
	if m.lease.ResourceID != resourceID || m.lease.OwnerID != ownerID || m.lease.FencingToken != fencingToken || !m.lease.LeaseExpiresAt.After(now) {
		return repository.ErrLeaseLost
	}
	m.lease.HeartbeatAt = now
	m.lease.LeaseExpiresAt = now.Add(ttl)
	return nil
}

func (m *mockResourceStore) ReleaseExecutionLease(ctx context.Context, resourceID uuid.UUID, ownerID string, fencingToken int64) error {
	if m.releaseLeaseErr != nil {
		return m.releaseLeaseErr
	}
	if m.lease.ResourceID != resourceID || m.lease.OwnerID != ownerID || m.lease.FencingToken != fencingToken {
		return repository.ErrLeaseLost
	}
	m.lease = model.ExecutionLease{}
	return nil
}

func (m *mockResourceStore) GetExecutionLease(ctx context.Context, resourceID uuid.UUID) (model.ExecutionLease, error) {
	if m.lease.ResourceID != resourceID {
		return model.ExecutionLease{}, repository.ErrResourceNotFound
	}
	return m.lease, nil
}

// WithLease variants delegate to base methods; fencing is exercised in integration tests.
func (m *mockResourceStore) TransitionStatusWithLease(ctx context.Context, id uuid.UUID, from []model.ResourceStatus, to model.ResourceStatus, ownerID string, fencingToken int64) error {
	return m.TransitionStatus(ctx, id, from, to)
}

func (m *mockResourceStore) SavePlanWithLease(ctx context.Context, resource model.InfrastructureResource, ownerID string, fencingToken int64) error {
	return m.SavePlan(ctx, resource)
}

func (m *mockResourceStore) SaveDestroyPlanWithLease(ctx context.Context, resource model.InfrastructureResource, ownerID string, fencingToken int64) error {
	return m.SaveDestroyPlan(ctx, resource)
}

func (m *mockResourceStore) FinishReviewedPlanWithLease(ctx context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus, succeeded bool, ownerID string, fencingToken int64) error {
	return m.FinishReviewedPlan(ctx, resource, operation, next, succeeded)
}

func TestCreateResourceSuccess(t *testing.T) {
	store := &mockResourceStore{}
	resourceService := NewResourceService(store)

	input := model.CreateResourceInput{
		ProjectID:    uuid.New().String(),
		Name:         "Production VPC",
		Description:  "Production network infrastructure",
		ResourceType: "aws_vpc",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		Environment:  "production",
		Configuration: map[string]any{
			"cidr_block": "10.0.0.0/16",
		},
	}

	resource, err := resourceService.Create(context.Background(), input)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if !store.createCalled {
		t.Fatal("expected repository Create to be called")
	}

	if resource.ID == uuid.Nil {
		t.Fatal("expected resource ID to be generated")
	}

	if resource.Name != "Production VPC" {
		t.Fatalf("expected resource name, got %s", resource.Name)
	}

	if resource.Status != model.ResourceStatusPending {
		t.Fatalf("expected pending status, got %s", resource.Status)
	}
}

func TestCreateResourceRejectsInvalidProvider(t *testing.T) {
	store := &mockResourceStore{}
	resourceService := NewResourceService(store)

	input := model.CreateResourceInput{
		Name:               "Production VPC",
		Provider:           "invalid-provider",
		Region:             "eu-west-1",
		Environment:        "production",
		TerraformDirectory: "terraform/aws/vpc",
	}

	_, err := resourceService.Create(context.Background(), input)

	if err == nil {
		t.Fatal("expected validation error, got nil")
	}

	if store.createCalled {
		t.Fatal("repository Create should not be called")
	}
}

func TestCreateResourceRejectsShortName(t *testing.T) {
	store := &mockResourceStore{}
	resourceService := NewResourceService(store)

	input := model.CreateResourceInput{
		Name:               "VC",
		Provider:           model.ProviderAWS,
		Region:             "eu-west-1",
		Environment:        "production",
		TerraformDirectory: "terraform/aws/vpc",
	}

	_, err := resourceService.Create(context.Background(), input)

	if err == nil {
		t.Fatal("expected validation error, got nil")
	}

	if store.createCalled {
		t.Fatal("repository Create should not be called")
	}
}

func TestListUsesDefaultLimit(t *testing.T) {
	store := &mockResourceStore{}
	resourceService := NewResourceService(store)

	resources, err := resourceService.List(context.Background(), 0, -10)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if resources == nil {
		t.Fatal("expected non-nil resource list")
	}
}

func TestUpdateRejectsClientManagedStatus(t *testing.T) {
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:     uuid.New(),
			Status: model.ResourceStatusPending,
		},
	}
	svc := NewResourceService(store)
	status := model.ResourceStatusFailed

	_, err := svc.Update(context.Background(), store.resource.ID,
		model.UpdateResourceInput{Status: &status})

	if err != ErrResourceStatusManaged {
		t.Fatalf("expected ErrResourceStatusManaged, got %v", err)
	}
	if store.updateCalled {
		t.Fatal("repository Update must not be called")
	}
}

func TestUpdateLocksSensitiveFieldsOutsidePendingOrFailed(t *testing.T) {
	statuses := []model.ResourceStatus{
		model.ResourceStatusPlanning,
		model.ResourceStatusAwaitingApproval,
		model.ResourceStatusProvisioning,
		model.ResourceStatusActive,
		model.ResourceStatusInactive,
		model.ResourceStatusDestroying,
		model.ResourceStatusDestroyed,
	}

	for _, status := range statuses {
		t.Run(string(status), func(t *testing.T) {
			store := &mockResourceStore{
				resource: model.InfrastructureResource{
					ID:     uuid.New(),
					Status: status,
					Region: "eu-west-1",
				},
			}
			svc := NewResourceService(store)
			region := "eu-central-1"

			_, err := svc.Update(context.Background(), store.resource.ID,
				model.UpdateResourceInput{Region: &region})

			if err != ErrProvisioningFieldsLocked {
				t.Fatalf("expected ErrProvisioningFieldsLocked, got %v", err)
			}
			if store.updateCalled {
				t.Fatal("repository Update must not be called")
			}
		})
	}
}

func TestUpdateAllowsDescriptionWhileAwaitingApproval(t *testing.T) {
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:          uuid.New(),
			Status:      model.ResourceStatusAwaitingApproval,
			Description: "Before",
		},
	}
	svc := NewResourceService(store)
	description := "Updated description"

	updated, err := svc.Update(context.Background(), store.resource.ID,
		model.UpdateResourceInput{Description: &description})

	if err != nil {
		t.Fatalf("expected description update to succeed, got %v", err)
	}
	if updated.Description != description {
		t.Fatalf("expected description %q, got %q", description, updated.Description)
	}
	if !store.updateCalled {
		t.Fatal("expected repository Update to be called")
	}
}

func TestUpdateAllowsConfigurationChangeWhenPending(t *testing.T) {
	store := &mockResourceStore{
		resource: model.InfrastructureResource{
			ID:     uuid.New(),
			Status: model.ResourceStatusPending,
			Region: "eu-west-1",
		},
	}
	svc := NewResourceService(store)
	region := "eu-central-1"
	configuration := map[string]any{"cidr_block": "10.70.0.0/16"}

	updated, err := svc.Update(context.Background(), store.resource.ID,
		model.UpdateResourceInput{
			Region:        &region,
			Configuration: configuration,
		})

	if err != nil {
		t.Fatalf("expected pending resource update to succeed, got %v", err)
	}
	if updated.Region != region {
		t.Fatalf("expected region %q, got %q", region, updated.Region)
	}
	if !store.updateCalled {
		t.Fatal("expected repository Update to be called")
	}
}

func (m *mockResourceStore) ReviewPlan(context.Context, uuid.UUID, model.PlanReviewInput, string) error {
	return nil
}
func (m *mockResourceStore) PlanReviews(context.Context, uuid.UUID) ([]model.PlanReview, error) {
	return nil, nil
}
func (m *mockResourceStore) InvalidatePlan(ctx context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus) error {
	from := model.ResourceStatusAwaitingApproval
	if operation == "destroy" {
		from = model.ResourceStatusAwaitingDestroyApproval
	}
	return m.TransitionStatus(ctx, resource.ID, []model.ResourceStatus{from}, next)
}
func (m *mockResourceStore) ClaimReviewedPlan(ctx context.Context, resource model.InfrastructureResource, operation, _ string) error {
	from, to := model.ResourceStatusAwaitingApproval, model.ResourceStatusProvisioning
	if operation == "destroy" {
		from, to = model.ResourceStatusAwaitingDestroyApproval, model.ResourceStatusDestroying
	}
	return m.TransitionStatus(ctx, resource.ID, []model.ResourceStatus{from}, to)
}
func (m *mockResourceStore) FinishReviewedPlan(ctx context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus, _ bool) error {
	from := model.ResourceStatusProvisioning
	if operation == "destroy" {
		from = model.ResourceStatusDestroying
	}
	return m.TransitionStatus(ctx, resource.ID, []model.ResourceStatus{from}, next)
}
