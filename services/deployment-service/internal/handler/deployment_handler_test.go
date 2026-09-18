package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
)

type mockDeploymentManager struct {
	createFunc  func(context.Context, model.CreateDeploymentInput) (model.Deployment, error)
	getByIDFunc func(context.Context, uuid.UUID) (model.Deployment, error)
	listFunc    func(context.Context, int, int) ([]model.Deployment, error)
	updateFunc  func(context.Context, uuid.UUID, model.UpdateDeploymentInput) (model.Deployment, error)
	deleteFunc  func(context.Context, uuid.UUID) error
}

func (m *mockDeploymentManager) Create(
	ctx context.Context,
	input model.CreateDeploymentInput,
) (model.Deployment, error) {
	if m.createFunc != nil {
		return m.createFunc(ctx, input)
	}

	return model.Deployment{}, nil
}

func (m *mockDeploymentManager) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.Deployment, error) {
	if m.getByIDFunc != nil {
		return m.getByIDFunc(ctx, id)
	}

	return model.Deployment{}, nil
}

func (m *mockDeploymentManager) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.Deployment, error) {
	if m.listFunc != nil {
		return m.listFunc(ctx, limit, offset)
	}

	return []model.Deployment{}, nil
}

func (m *mockDeploymentManager) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateDeploymentInput,
) (model.Deployment, error) {
	if m.updateFunc != nil {
		return m.updateFunc(ctx, id, input)
	}

	return model.Deployment{}, nil
}

func (m *mockDeploymentManager) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if m.deleteFunc != nil {
		return m.deleteFunc(ctx, id)
	}

	return nil
}

func testDeployment() model.Deployment {
	now := time.Now().UTC()

	return model.Deployment{
		ID:           uuid.New(),
		ProjectID:    uuid.New(),
		Environment:  "production",
		Image:        "nginx:1.27",
		GitCommitSHA: "abcdef1234567",
		Namespace:    "production",
		Status:       model.DeploymentStatusPending,
		CreatedAt:    now,
		UpdatedAt:    now,
	}
}

func TestHealth(t *testing.T) {
	h := NewDeploymentHandler(&mockDeploymentManager{})

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()

	h.Health(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	if !strings.Contains(rec.Body.String(), "deployment-service") {
		t.Fatalf("expected service name in response, got %s", rec.Body.String())
	}
}

func TestCreateDeployment(t *testing.T) {
	expected := testDeployment()

	manager := &mockDeploymentManager{
		createFunc: func(
			ctx context.Context,
			input model.CreateDeploymentInput,
		) (model.Deployment, error) {
			return expected, nil
		},
	}

	h := NewDeploymentHandler(manager)

	body := `{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"environment": "production",
		"image": "nginx:1.27",
		"git_commit_sha": "abcdef1234567",
		"namespace": "production"
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/deployments",
		strings.NewReader(body),
	)
	req.Header.Set("Content-Type", "application/json")

	rec := httptest.NewRecorder()

	h.Create(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", rec.Code)
	}

	var response model.Deployment

	if err := json.NewDecoder(rec.Body).Decode(&response); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if response.ID != expected.ID {
		t.Fatalf("expected ID %s, got %s", expected.ID, response.ID)
	}
}

func TestCreateDeploymentInvalidJSON(t *testing.T) {
	h := NewDeploymentHandler(&mockDeploymentManager{})

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/deployments",
		strings.NewReader(`{"environment":`),
	)

	rec := httptest.NewRecorder()

	h.Create(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
}

func TestCreateDeploymentUnknownField(t *testing.T) {
	h := NewDeploymentHandler(&mockDeploymentManager{})

	body := `{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"environment": "production",
		"image": "nginx:1.27",
		"git_commit_sha": "abcdef1234567",
		"namespace": "production",
		"unexpected": true
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/deployments",
		strings.NewReader(body),
	)

	rec := httptest.NewRecorder()

	h.Create(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
}

func TestListDeployments(t *testing.T) {
	manager := &mockDeploymentManager{
		listFunc: func(
			ctx context.Context,
			limit int,
			offset int,
		) ([]model.Deployment, error) {
			return []model.Deployment{testDeployment()}, nil
		},
	}

	h := NewDeploymentHandler(manager)

	req := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments?limit=10&offset=5",
		nil,
	)

	rec := httptest.NewRecorder()

	h.List(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	if !strings.Contains(rec.Body.String(), `"limit":10`) {
		t.Fatalf("expected limit in response, got %s", rec.Body.String())
	}

	if !strings.Contains(rec.Body.String(), `"offset":5`) {
		t.Fatalf("expected offset in response, got %s", rec.Body.String())
	}
}

func TestListDeploymentsInvalidLimit(t *testing.T) {
	h := NewDeploymentHandler(&mockDeploymentManager{})

	req := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments?limit=abc",
		nil,
	)

	rec := httptest.NewRecorder()

	h.List(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
}

func TestListDeploymentsInvalidOffset(t *testing.T) {
	h := NewDeploymentHandler(&mockDeploymentManager{})

	req := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments?offset=-1",
		nil,
	)

	rec := httptest.NewRecorder()

	h.List(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
}

func TestGetDeployment(t *testing.T) {
	expected := testDeployment()

	manager := &mockDeploymentManager{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return expected, nil
		},
	}

	h := NewDeploymentHandler(manager)

	req := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/"+expected.ID.String(),
		nil,
	)

	req.SetPathValue("id", expected.ID.String())

	rec := httptest.NewRecorder()

	h.GetByID(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
}

func TestGetDeploymentInvalidID(t *testing.T) {
	h := NewDeploymentHandler(&mockDeploymentManager{})

	req := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/invalid",
		nil,
	)

	req.SetPathValue("id", "invalid")

	rec := httptest.NewRecorder()

	h.GetByID(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
}

func TestGetDeploymentNotFound(t *testing.T) {
	manager := &mockDeploymentManager{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return model.Deployment{}, repository.ErrDeploymentNotFound
		},
	}

	h := NewDeploymentHandler(manager)

	id := uuid.New()

	req := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/"+id.String(),
		nil,
	)

	req.SetPathValue("id", id.String())

	rec := httptest.NewRecorder()

	h.GetByID(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", rec.Code)
	}
}

func TestUpdateDeployment(t *testing.T) {
	expected := testDeployment()

	manager := &mockDeploymentManager{
		updateFunc: func(
			ctx context.Context,
			id uuid.UUID,
			input model.UpdateDeploymentInput,
		) (model.Deployment, error) {
			return expected, nil
		},
	}

	h := NewDeploymentHandler(manager)

	body := `{"image":"nginx:1.28"}`

	req := httptest.NewRequest(
		http.MethodPatch,
		"/api/v1/deployments/"+expected.ID.String(),
		strings.NewReader(body),
	)

	req.SetPathValue("id", expected.ID.String())

	rec := httptest.NewRecorder()

	h.Update(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}
}

func TestDeleteDeployment(t *testing.T) {
	id := uuid.New()

	manager := &mockDeploymentManager{
		deleteFunc: func(
			ctx context.Context,
			deploymentID uuid.UUID,
		) error {
			if deploymentID != id {
				t.Fatalf("expected ID %s, got %s", id, deploymentID)
			}

			return nil
		},
	}

	h := NewDeploymentHandler(manager)

	req := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/deployments/"+id.String(),
		nil,
	)

	req.SetPathValue("id", id.String())

	rec := httptest.NewRecorder()

	h.Delete(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected status 204, got %d", rec.Code)
	}
}

func TestDeleteDeploymentNotFound(t *testing.T) {
	manager := &mockDeploymentManager{
		deleteFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) error {
			return repository.ErrDeploymentNotFound
		},
	}

	h := NewDeploymentHandler(manager)

	id := uuid.New()

	req := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/deployments/"+id.String(),
		nil,
	)

	req.SetPathValue("id", id.String())

	rec := httptest.NewRecorder()

	h.Delete(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", rec.Code)
	}
}

func TestWriteServiceErrorInternalError(t *testing.T) {
	h := NewDeploymentHandler(&mockDeploymentManager{})

	manager := &mockDeploymentManager{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return model.Deployment{}, errors.New("database unavailable")
		},
	}

	h = NewDeploymentHandler(manager)

	req := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/"+uuid.New().String(),
		nil,
	)

	req.SetPathValue("id", uuid.New().String())

	rec := httptest.NewRecorder()

	h.GetByID(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected status 500, got %d", rec.Code)
	}
}
