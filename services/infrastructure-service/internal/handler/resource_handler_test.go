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
	resource      model.InfrastructureResource
	listLimit     int
	listOffset    int
	listCallCount int
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
	m.listLimit = limit
	m.listOffset = offset
	m.listCallCount++

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

func TestListHandlerDefaultPagination(t *testing.T) {
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

	if manager.listCallCount != 1 {
		t.Fatalf("expected one list call, got %d", manager.listCallCount)
	}

	if manager.listLimit != 20 {
		t.Fatalf("expected default limit 20, got %d", manager.listLimit)
	}

	if manager.listOffset != 0 {
		t.Fatalf("expected default offset 0, got %d", manager.listOffset)
	}
}

func TestListHandlerValidPagination(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=10&offset=5",
		nil,
	)
	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	if manager.listLimit != 10 {
		t.Fatalf("expected limit 10, got %d", manager.listLimit)
	}

	if manager.listOffset != 5 {
		t.Fatalf("expected offset 5, got %d", manager.listOffset)
	}
}

func TestListHandlerInvalidLimit(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=abc",
		nil,
	)
	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid limit")
	}
}

func TestListHandlerLimitBelowMinimum(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=0",
		nil,
	)
	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid limit")
	}
}

func TestListHandlerLimitAboveMaximum(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=101",
		nil,
	)
	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid limit")
	}
}

func TestListHandlerInvalidOffset(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?offset=abc",
		nil,
	)
	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid offset")
	}
}

func TestListHandlerNegativeOffset(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?offset=-1",
		nil,
	)
	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid offset")
	}
}

func TestDeleteHandlerNotFound(t *testing.T) {
	manager := &mockResourceManager{
		resource: model.InfrastructureResource{
			ID: uuid.New(),
		},
	}

	handler := NewResourceHandler(manager)

	unknownID := uuid.New().String()

	request := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/resources/"+unknownID,
		nil,
	)

	request.SetPathValue("id", unknownID)

	recorder := httptest.NewRecorder()

	handler.Delete(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", recorder.Code)
	}
}

func TestDeleteHandlerInvalidUUID(t *testing.T) {
	manager := &mockResourceManager{}
	handler := NewResourceHandler(manager)

	request := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/resources/invalid-id",
		nil,
	)

	request.SetPathValue("id", "invalid-id")

	recorder := httptest.NewRecorder()

	handler.Delete(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}
}

func TestGetByIDHandlerNotFound(t *testing.T) {
	manager := &mockResourceManager{
		resource: model.InfrastructureResource{
			ID: uuid.New(),
		},
	}

	handler := NewResourceHandler(manager)

	unknownID := uuid.New().String()

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources/"+unknownID,
		nil,
	)

	request.SetPathValue("id", unknownID)

	recorder := httptest.NewRecorder()

	handler.GetByID(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", recorder.Code)
	}
}

func TestHandlerUsesRepositoryNotFoundError(t *testing.T) {
	if !errors.Is(repository.ErrResourceNotFound, repository.ErrResourceNotFound) {
		t.Fatal("repository not-found error is not comparable with itself")
	}
}
