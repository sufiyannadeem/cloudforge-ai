package handler

import (
	"context"
	"encoding/json"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type emptyInventoryManager struct{ mockResourceManager }

func (*emptyInventoryManager) List(context.Context, int, int) ([]model.InfrastructureResource, error) {
	return nil, nil
}

func TestSignedDeveloperEmptyInventoryInReadOnlyEnvironment(t *testing.T) {
	const key = "inventory-test-key-at-least-32-bytes"
	handler := NewResourceHandler(&emptyInventoryManager{}, &mockProvisioningManager{})
	handler.TerraformReadOnly = true
	router := NewAuthenticatedRouter(handler, key, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/resources?limit=100", nil)
	now := time.Now().Unix()
	req.Header.Set(identity.Header, identity.Sign(identity.Claims{
		Issuer: "frontend", Audience: "infrastructure", Subject: "no-projects", Role: "developer",
		Method: req.Method, Target: req.URL.RequestURI(), Issued: now, Expiry: now + 25,
		Nonce: "0123456789abcdef0123456789abcdef",
	}, key))
	response := httptest.NewRecorder()
	router.ServeHTTP(response, req)
	var body struct{ Items []json.RawMessage }
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil || response.Code != 200 || body.Items == nil || len(body.Items) != 0 {
		t.Fatalf("inventory: %d %s (%v)", response.Code, response.Body.String(), err)
	}
	req.Header.Del(identity.Header)
	response = httptest.NewRecorder()
	router.ServeHTTP(response, req)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("unsigned inventory: %d", response.Code)
	}
}

func TestReadOnlyEnvironmentBlocksTerraformOperations(t *testing.T) {
	handler := NewResourceHandler(&mockResourceManager{}, &mockProvisioningManager{})
	handler.TerraformReadOnly = true
	router := newResourceMux(handler)
	for _, action := range []string{"plan", "apply", "destroy/plan", "destroy/apply", "drift"} {
		request := httptest.NewRequest(http.MethodPost, "/api/v1/resources/"+uuid.NewString()+"/"+action, nil)
		response := httptest.NewRecorder()
		router.ServeHTTP(response, request)
		if response.Code != http.StatusServiceUnavailable {
			t.Errorf("%s: %d", action, response.Code)
		}
	}
}
