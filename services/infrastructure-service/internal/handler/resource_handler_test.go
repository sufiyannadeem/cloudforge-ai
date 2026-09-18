package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
)

type mockResourceManager struct {
	resource model.InfrastructureResource
}

func (m *mockResourceManager) Create(
	ctx context.Context,
	input model.CreateResourceInput,
) (model.InfrastructureResource, error) {
	m.resource = model.InfrastructureResource{
		ID:       uuid.New(),
		Name:     input.Name,
		Provider: input.Provider,
		Region:   input.Region,
		Status:   model.ResourceStatusActive,
	}

	return m.resource, nil
}

func (m *mockResourceManager) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	if id != m.resource.ID {
		return model.InfrastructureResource{}, repository.ErrResourceNotFound
	}

	return m.resource, nil
}

func (m *mockResourceManager) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.InfrastructureResource, error) {
	return []model.InfrastructureResource{m.resource}, nil
}

func (m *mockResourceManager) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateResourceInput,
) (model.InfrastructureResource, error) {
	return m.resource, nil
}

func (m *mockResourceManager) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if id != m.resource.ID {
		return repository.ErrResourceNotFound
	}

	return nil
}

func TestHealthHandler(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()

	handler.Health(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	var response map[string]string

	if err := json.NewDecoder(recorder.Body).Decode(&response); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if response["status"] != "ok" {
		t.Fatalf("expected status ok, got %s", response["status"])
	}
}

func TestCreateHandler(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	body := `{
		"name": "Production VPC",
		"description": "Production network",
		"provider": "aws",
		"region": "eu-west-1",
		"environment": "production",
		"terraform_directory": "terraform/aws/vpc"
	}`

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources",
		strings.NewReader(body),
	)
	recorder := httptest.NewRecorder()

	handler.Create(recorder, request)

	if recorder.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", recorder.Code)
	}

	if manager.resource.Name != "Production VPC" {
		t.Fatalf("unexpected resource name: %s", manager.resource.Name)
	}
}

func TestCreateHandlerInvalidJSON(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources",
		strings.NewReader(`{"name":`),
	)
	recorder := httptest.NewRecorder()

	handler.Create(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}
}

func TestGetByIDHandlerInvalidUUID(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources/invalid-id",
		nil,
	)
	request.SetPathValue("id", "invalid-id")

	recorder := httptest.NewRecorder()

	handler.GetByID(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}
}

func TestListHandler(t *testing.T) {
	manager := &mockResourceManager{
		resource: model.InfrastructureResource{
			ID:       uuid.New(),
			Name:     "Production VPC",
			Provider: model.ProviderAWS,
		},
	}

	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources",
		nil,
	)
	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}
}

func TestDeleteHandlerNotFound(t *testing.T) {
	manager := &mockResourceManager{
		resource: model.InfrastructureResource{
			ID: uuid.New(),
		},
	}

	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/resources/"+uuid.New().String(),
		nil,
	)

	request.SetPathValue("id", uuid.New().String())

	recorder := httptest.NewRecorder()

	handler.Delete(recorder, request)

	if !errors.Is(repository.ErrResourceNotFound, repository.ErrResourceNotFound) {
		t.Fatal("unexpected repository error")
	}

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", recorder.Code)
	}
}
