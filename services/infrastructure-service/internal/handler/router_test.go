package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func TestNewRouterHealthRoute(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/health",
		nil,
	)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}
}

func TestNewRouterCreateResourceRoute(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

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
	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", recorder.Code)
	}
}

func TestNewRouterListResourceRoute(t *testing.T) {
	manager := &mockResourceManager{
		resource: createRouterTestResource(),
	}

	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=10&offset=0",
		nil,
	)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	if manager.listLimit != 10 {
		t.Fatalf("expected limit 10, got %d", manager.listLimit)
	}

	if manager.listOffset != 0 {
		t.Fatalf("expected offset 0, got %d", manager.listOffset)
	}
}

func TestNewRouterGetResourceRoute(t *testing.T) {
	resource := createRouterTestResource()

	manager := &mockResourceManager{
		resource: resource,
	}

	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources/"+resource.ID.String(),
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}
}

func TestNewRouterGetResourceInvalidUUID(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources/invalid-id",
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}
}

func TestNewRouterUpdateResourceRoute(t *testing.T) {
	resource := createRouterTestResource()

	manager := &mockResourceManager{
		resource: resource,
	}

	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	body := `{
		"description": "Updated infrastructure description"
	}`

	request := httptest.NewRequest(
		http.MethodPatch,
		"/api/v1/resources/"+resource.ID.String(),
		strings.NewReader(body),
	)
	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}
}

func TestNewRouterDeleteResourceRoute(t *testing.T) {
	resource := createRouterTestResource()

	manager := &mockResourceManager{
		resource: resource,
	}

	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	request := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/resources/"+resource.ID.String(),
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNoContent {
		t.Fatalf("expected status 204, got %d", recorder.Code)
	}
}

func TestNewRouterUnsupportedMethod(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	request := httptest.NewRequest(
		http.MethodPut,
		"/api/v1/resources",
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected status 405, got %d", recorder.Code)
	}
}

func TestNewRouterUnknownRoute(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := NewResourceHandler(manager)
	router := NewRouter(resourceHandler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/unknown",
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", recorder.Code)
	}
}

func createRouterTestResource() model.InfrastructureResource {
	return model.InfrastructureResource{
		ID:       uuid.New(),
		Name:     "Production VPC",
		Provider: model.ProviderAWS,
		Region:   "eu-west-1",
		Status:   model.ResourceStatusActive,
	}
}
