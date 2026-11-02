package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func newRouterTestHandler(
	manager *mockResourceManager,
) *ResourceHandler {
	return NewResourceHandler(
		manager,
		&mockProvisioningManager{},
	)
}

func TestNewRouterHealthRoute(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

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
	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

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

	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

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

	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

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
	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

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

	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

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

	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

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

func TestNewRouterPlanResourceRoute(t *testing.T) {
	resource := createRouterTestResource()

	manager := &mockResourceManager{
		resource: resource,
	}

	provisioning := &mockProvisioningManager{
		resource: resource,
	}

	resourceHandler := NewResourceHandler(
		manager,
		provisioning,
	)
	router := newResourceMux(resourceHandler)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+resource.ID.String()+"/plan",
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status 200, got %d",
			recorder.Code,
		)
	}

	if provisioning.planCallCount != 1 {
		t.Fatalf(
			"expected one plan call, got %d",
			provisioning.planCallCount,
		)
	}

	if provisioning.lastPlanID != resource.ID {
		t.Fatalf(
			"expected plan ID %s, got %s",
			resource.ID,
			provisioning.lastPlanID,
		)
	}
}

func TestNewRouterGetPlanResourceRoute(t *testing.T) {
	resource := createRouterTestResource()
	manager := &mockResourceManager{resource: resource}
	provisioning := &mockProvisioningManager{
		resource: resource,
	}

	resourceHandler := NewResourceHandler(manager, provisioning)
	router := newResourceMux(resourceHandler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources/"+resource.ID.String()+"/plan",
		nil,
	)

	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestNewRouterApplyResourceRoute(t *testing.T) {
	resource := createRouterTestResource()

	manager := &mockResourceManager{
		resource: resource,
	}

	provisioning := &mockProvisioningManager{
		resource: resource,
	}

	resourceHandler := NewResourceHandler(
		manager,
		provisioning,
	)
	router := newResourceMux(resourceHandler)

	planHash := "test-plan-hash"

	body := `{"plan_hash":"` + planHash + `"}`

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+resource.ID.String()+"/apply",
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status 200, got %d",
			recorder.Code,
		)
	}

	if provisioning.applyCallCount != 1 {
		t.Fatalf(
			"expected one apply call, got %d",
			provisioning.applyCallCount,
		)
	}

	if provisioning.lastApplyID != resource.ID {
		t.Fatalf(
			"expected apply ID %s, got %s",
			resource.ID,
			provisioning.lastApplyID,
		)
	}

	if provisioning.lastPlanHash != planHash {
		t.Fatalf(
			"expected plan hash %s, got %s",
			planHash,
			provisioning.lastPlanHash,
		)
	}
}

func TestNewRouterUnsupportedMethod(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

	request := httptest.NewRequest(
		http.MethodPut,
		"/api/v1/resources",
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusMethodNotAllowed {
		t.Fatalf(
			"expected status 405, got %d",
			recorder.Code,
		)
	}
}

func TestNewRouterUnknownRoute(t *testing.T) {
	manager := &mockResourceManager{}
	resourceHandler := newRouterTestHandler(manager)
	router := newResourceMux(resourceHandler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/unknown",
		nil,
	)

	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf(
			"expected status 404, got %d",
			recorder.Code,
		)
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

func TestAuthenticatedRouterRejectsMissingAndInvalidToken(t *testing.T) {
	resourceHandler := newRouterTestHandler(&mockResourceManager{})
	router := NewRouterWithInternalToken(resourceHandler, "01234567890123456789012345678901")

	for _, token := range []string{"", "wrong-token"} {
		request := httptest.NewRequest(http.MethodGet, "/api/v1/resources", nil)
		if token != "" {
			request.Header.Set("X-CloudForge-Internal-Token", token)
		}
		recorder := httptest.NewRecorder()
		router.ServeHTTP(recorder, request)
		if recorder.Code != http.StatusUnauthorized {
			t.Fatalf("token %q: expected 401, got %d", token, recorder.Code)
		}
	}
}

func TestAuthenticatedRouterAllowsHealthWithoutToken(t *testing.T) {
	resourceHandler := newRouterTestHandler(&mockResourceManager{})
	router := NewRouterWithInternalToken(resourceHandler, "01234567890123456789012345678901")
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected health endpoint to return 200, got %d", recorder.Code)
	}
}

func TestAuthenticatedRouterAllowsValidToken(t *testing.T) {
	resourceHandler := newRouterTestHandler(&mockResourceManager{})
	token := "01234567890123456789012345678901"
	router := NewRouterWithInternalToken(resourceHandler, token)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/resources?limit=10", nil)
	request.Header.Set("X-CloudForge-Internal-Token", token)
	request.Header.Set("X-CloudForge-Role", "viewer")
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected valid token to return 200, got %d", recorder.Code)
	}
}

func TestAuthenticatedRouterRejectsViewerMutation(t *testing.T) {
	resourceHandler := newRouterTestHandler(&mockResourceManager{})
	token := "01234567890123456789012345678901"
	router := NewRouterWithInternalToken(resourceHandler, token)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/resources", strings.NewReader(`{}`))
	request.Header.Set("X-CloudForge-Internal-Token", token)
	request.Header.Set("X-CloudForge-Role", "viewer")
	request.Header.Set("X-CloudForge-Actor", "test-operator")
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("expected viewer mutation to return 403, got %d", recorder.Code)
	}
}

func TestAuthenticatedRouterRejectsDevOpsApply(t *testing.T) {
	resourceHandler := newRouterTestHandler(&mockResourceManager{})
	token := "01234567890123456789012345678901"
	router := NewRouterWithInternalToken(resourceHandler, token)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/resources/resource-id/apply", strings.NewReader(`{"plan_hash":"hash"}`))
	request.Header.Set("X-CloudForge-Internal-Token", token)
	request.Header.Set("X-CloudForge-Role", "devops")
	request.Header.Set("X-CloudForge-Actor", "test-operator")
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("expected DevOps apply to return 403, got %d", recorder.Code)
	}
}
