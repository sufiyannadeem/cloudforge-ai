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
	createCalled bool
	created      model.InfrastructureResource
	resource     model.InfrastructureResource
	updated      model.InfrastructureResource
	updateCalled bool
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
	_ = ctx
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
