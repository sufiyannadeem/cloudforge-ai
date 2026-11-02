package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

const testInternalToken = "0123456789abcdef0123456789abcdef" // 32 characters

func setupTestRouter(mgr *mockDeploymentManager) http.Handler {
	if mgr == nil {
		mgr = &mockDeploymentManager{}
	}

	h := NewDeploymentHandler(mgr)
	mux := NewRouter(h)

	return NewRouterWithInternalToken(mux, testInternalToken)
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

	router := NewRouterWithInternalToken(mux, testInternalToken)

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

func TestRouterRejectsMissingToken(t *testing.T) {
	router := setupTestRouter(nil)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/deployments", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected status 401, got %d", rec.Code)
	}
}

func TestRouterRejectsShortToken(t *testing.T) {
	mgr := &mockDeploymentManager{}
	h := NewDeploymentHandler(mgr)
	mux := NewRouter(h)

	// Router with token shorter than 32 characters
	router := NewRouterWithInternalToken(mux, "short-token")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/deployments", nil)
	req.Header.Set("X-CloudForge-Internal-Token", "short-token")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected status 401 for short token, got %d", rec.Code)
	}
}

func TestRouterRejectsMismatchedToken(t *testing.T) {
	router := setupTestRouter(nil)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/deployments", nil)
	req.Header.Set("X-CloudForge-Internal-Token", "wrong-token-32-chars-long-abcdef")
	req.Header.Set("X-CloudForge-Role", "viewer")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected status 401, got %d", rec.Code)
	}
}

func TestRouterAllowsViewerForGet(t *testing.T) {
	mgr := &mockDeploymentManager{
		listFunc: func(ctx context.Context, limit, offset int) ([]model.Deployment, error) {
			return []model.Deployment{}, nil
		},
	}
	router := setupTestRouter(mgr)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/deployments", nil)
	req.Header.Set("X-CloudForge-Internal-Token", testInternalToken)
	req.Header.Set("X-CloudForge-Role", "viewer")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
}

func TestRouterRejectsViewerForMutations(t *testing.T) {
	router := setupTestRouter(nil)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/deployments", strings.NewReader(`{}`))
	req.Header.Set("X-CloudForge-Internal-Token", testInternalToken)
	req.Header.Set("X-CloudForge-Role", "viewer")
	req.Header.Set("X-CloudForge-Actor", "user-123")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected status 403 for viewer mutation, got %d", rec.Code)
	}
}

func TestRouterRejectsMutationWithoutActor(t *testing.T) {
	router := setupTestRouter(nil)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/deployments", strings.NewReader(`{}`))
	req.Header.Set("X-CloudForge-Internal-Token", testInternalToken)
	req.Header.Set("X-CloudForge-Role", "devops")
	// Missing X-CloudForge-Actor
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected status 403 when actor is missing, got %d", rec.Code)
	}
}

func TestRouterAllowsDevOpsForCreate(t *testing.T) {
	mgr := &mockDeploymentManager{
		createFunc: func(ctx context.Context, input model.CreateDeploymentInput) (model.Deployment, error) {
			return testDeployment(), nil
		},
	}
	router := setupTestRouter(mgr)

	body := `{"project_id":"` + uuid.New().String() + `","environment":"production","image":"nginx:1.27","git_commit_sha":"abcdef1234567","namespace":"prod"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/deployments", strings.NewReader(body))
	req.Header.Set("X-CloudForge-Internal-Token", testInternalToken)
	req.Header.Set("X-CloudForge-Role", "devops")
	req.Header.Set("X-CloudForge-Actor", "operator-1")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", rec.Code)
	}
}

func TestRouterLeastPrivilegeRejectsDevOpsForDelete(t *testing.T) {
	router := setupTestRouter(nil)

	id := uuid.New().String()
	req := httptest.NewRequest(http.MethodDelete, "/api/v1/deployments/"+id, nil)
	req.Header.Set("X-CloudForge-Internal-Token", testInternalToken)
	req.Header.Set("X-CloudForge-Role", "devops")
	req.Header.Set("X-CloudForge-Actor", "operator-1")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected status 403 for devops delete, got %d", rec.Code)
	}
}

func TestRouterLeastPrivilegeAllowsPlatformEngineerForDelete(t *testing.T) {
	mgr := &mockDeploymentManager{
		deleteFunc: func(ctx context.Context, id uuid.UUID) error {
			return nil
		},
	}
	router := setupTestRouter(mgr)

	id := uuid.New().String()
	req := httptest.NewRequest(http.MethodDelete, "/api/v1/deployments/"+id, nil)
	req.Header.Set("X-CloudForge-Internal-Token", testInternalToken)
	req.Header.Set("X-CloudForge-Role", "platform-engineer")
	req.Header.Set("X-CloudForge-Actor", "lead-engineer")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected status 204, got %d", rec.Code)
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
	req.Header.Set("X-CloudForge-Internal-Token", testInternalToken)
	req.Header.Set("X-CloudForge-Role", "sre")
	req.Header.Set("X-CloudForge-Actor", "oncall-sre")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", rec.Code)
	}
}
