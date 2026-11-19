package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"context"
	"crypto/sha256"
	"fmt"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
	"time"
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

func TestInfrastructureRBACAndApprovalReplay(t *testing.T) {
	const key = "test-infrastructure-key-at-least-32-bytes"
	used := map[string]bool{}
	router := NewAuthenticatedRouter(newRouterTestHandler(&mockResourceManager{}), key,
		func(_ context.Context, caller identity.Claims) error {
			if caller.Subject != "verified-operator" {
				t.Fatal("forged actor reached approval processing")
			}
			if used[caller.Nonce] {
				return identity.ErrReplay
			}
			used[caller.Nonce] = true
			return nil
		})
	id := uuid.NewString()
	apply := "/api/v1/resources/" + id + "/apply"
	body := `{"plan_hash":"test"}`
	digest := fmt.Sprintf("%x", sha256.Sum256([]byte(body)))
	now := time.Now().Unix()
	for _, tc := range []struct {
		method, path, role, sentBody string
		status                       int
	}{
		{"GET", "/health", "", "", 200},
		{"GET", "/api/v1/resources", "", "", 401},
		{"POST", "/api/v1/resources", "sre", "", 403},
		{"DELETE", "/api/v1/resources/" + id, "developer", "", 403},
		{"POST", apply, "platform-engineer", "changed", 403},
		{"POST", apply, "platform-engineer", body, 200},
		{"POST", apply, "platform-engineer", body, 409},
	} {
		req := httptest.NewRequest(tc.method, tc.path, strings.NewReader(tc.sentBody))
		req.Header.Set("X-CloudForge-Role", "platform-engineer")
		req.Header.Set("X-CloudForge-Actor", "forged")
		if tc.role != "" {
			req.Header.Set(identity.Header, identity.Sign(identity.Claims{
				Issuer: "frontend", Audience: "infrastructure", Role: tc.role, Subject: "verified-operator",
				Method: tc.method, Target: req.URL.RequestURI(), Issued: now, Expiry: now + 25,
				Nonce: "0123456789abcdef0123456789abcdef", Body: digest,
			}, key))
		}
		res := httptest.NewRecorder()
		router.ServeHTTP(res, req)
		if res.Code != tc.status {
			t.Errorf("%s %s as %q got %d want %d", tc.method, tc.path, tc.role, res.Code, tc.status)
		}
	}
}
