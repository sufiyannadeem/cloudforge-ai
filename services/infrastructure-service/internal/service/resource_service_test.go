package service

import (
	"context"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
)

type mockResourceStore struct {
	createCalled bool
	created      model.InfrastructureResource
}

func (m *mockResourceStore) Create(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	m.createCalled = true
	m.created = resource
	return nil
}

func (m *mockResourceStore) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	return model.InfrastructureResource{}, repository.ErrResourceNotFound
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
	return nil
}

func (m *mockResourceStore) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	return nil
}

func TestCreateResourceSuccess(t *testing.T) {
	store := &mockResourceStore{}
	resourceService := NewResourceService(store)

	input := model.CreateResourceInput{
		Name:               "Production VPC",
		Description:        "Production network infrastructure",
		Provider:           model.ProviderAWS,
		Region:             "eu-west-1",
		Environment:        "production",
		TerraformDirectory: "terraform/aws/vpc",
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

	if resource.Status != model.ResourceStatusActive {
		t.Fatalf("expected active status, got %s", resource.Status)
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
