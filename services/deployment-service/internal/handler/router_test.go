package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
	"time"
)

const testFrontendKey = "frontend-test-key-0123456789abcdef"
const testAIOpsKey = "aiops-test-key-0123456789abcdef012"

func signDeploymentRequest(req *http.Request, caller, key, role string) {
	now := time.Now().Unix()
	subject := ""
	if role != "" {
		subject = "operator"
	}
	req.Header.Set(identity.Header, identity.Sign(identity.Claims{
		Issuer: caller, Audience: "deployment", Subject: subject, Role: role,
		Method: req.Method, Target: req.URL.RequestURI(), Issued: now, Expiry: now + 25,
		Nonce: "0123456789abcdef0123456789abcdef",
	}, key))
}

func setupTestRouter(mgr *mockDeploymentManager) http.Handler {
	if mgr == nil {
		mgr = &mockDeploymentManager{}
	}

	h := NewDeploymentHandler(mgr)
	mux := NewRouter(h)

	return NewAuthenticatedRouter(mux, testFrontendKey, testAIOpsKey)
}

func TestRouterHealthBypassesAuth(t *testing.T) {
	router := setupTestRouter(nil)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
}

func TestRouterMetricsBypassesAuth(t *testing.T) {
	mgr := &mockDeploymentManager{}
	h := NewDeploymentHandler(mgr)
	mux := NewRouterWithDependenciesAndMetrics(h, nil, nil, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("metrics_data"))
	}))

	router := NewAuthenticatedRouter(mux, testFrontendKey, testAIOpsKey)

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
}

func TestRouterOpenAPIBypassesAuth(t *testing.T) {
	router := setupTestRouter(nil)

	req := httptest.NewRequest(http.MethodGet, "/openapi.yaml", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
}

func TestDeploymentCallerScope(t *testing.T) {
	router := NewAuthenticatedRouter(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}), testFrontendKey, testAIOpsKey)
	target := "/api/v1/deployments/" + uuid.NewString()
	for _, tc := range []struct {
		method, path, issuer, key, role string
		status                          int
	}{
		{"GET", target, "", "", "", 401},
		{"GET", target, "frontend", testFrontendKey, "developer", 503},
		{"DELETE", target, "frontend", testFrontendKey, "developer", 403},
		{"DELETE", target, "frontend", testFrontendKey, "platform-engineer", 204},
		{"GET", target + "/attempts", "aiops", testAIOpsKey, "", 204},
		{"GET", "/api/v1/deployments?limit=10", "aiops", testAIOpsKey, "", 204},
		{"POST", target + "/run", "aiops", testAIOpsKey, "", 403},
		{"POST", target + "/run", "aiops", testAIOpsKey, "platform-engineer", 403},
		{"POST", target + "/run", "frontend", testAIOpsKey, "platform-engineer", 401},
		{"POST", target + "/remediation-run", "frontend", testFrontendKey, "platform-engineer", 403},
	} {
		req := httptest.NewRequest(tc.method, tc.path, nil)
		req.Header.Set("X-CloudForge-Role", "platform-engineer")
		req.Header.Set("X-CloudForge-Actor", "forged")
		if tc.key != "" {
			signDeploymentRequest(req, tc.issuer, tc.key, tc.role)
		}
		res := httptest.NewRecorder()
		router.ServeHTTP(res, req)
		if res.Code != tc.status {
			t.Errorf("%s %s as %q: got %d want %d", tc.method, tc.path, tc.issuer, res.Code, tc.status)
		}
	}
}

func TestRouterRollbackRoute(t *testing.T) {
	id := uuid.New()
	mgr := &mockDeploymentManager{
		rollbackFunc: func(ctx context.Context, depID uuid.UUID) (model.Deployment, error) {
			d := testDeployment()
			d.ID = uuid.New()
			d.Image = "nginx:1.27-rolledback"
			return d, nil
		},
	}
	router := setupTestRouter(mgr)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/deployments/"+id.String()+"/rollback", nil)
	signDeploymentRequest(req, "frontend", testFrontendKey, "platform-engineer")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", rec.Code)
	}
}

func TestAuthenticatedRouterPreservesRegisteredPatternForMetrics(t *testing.T) {
	const path = "/api/v1/deployments"
	mux := http.NewServeMux()
	mux.HandleFunc("GET "+path, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	router := NewAuthenticatedRouter(mux, testFrontendKey, testAIOpsKey)
	request := httptest.NewRequest(http.MethodGet, path, nil)
	signDeploymentRequest(request, "frontend", testFrontendKey, "sre")
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK || request.Pattern != "GET "+path {
		t.Fatalf("status = %d, registered pattern = %q", recorder.Code, request.Pattern)
	}
}
