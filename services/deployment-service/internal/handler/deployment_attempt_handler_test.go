package handler

import (
	"context"
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

type mockDeploymentAttemptStore struct {
	listFunc func(
		context.Context,
		uuid.UUID,
		int,
		int,
	) ([]model.DeploymentAttempt, error)
}

func (m *mockDeploymentAttemptStore) Create(
	ctx context.Context,
	attempt model.DeploymentAttempt,
) error {
	return nil
}

func (m *mockDeploymentAttemptStore) Update(
	ctx context.Context,
	attempt model.DeploymentAttempt,
) error {
	return nil
}

func (m *mockDeploymentAttemptStore) GetNextAttemptNumber(
	ctx context.Context,
	deploymentID uuid.UUID,
) (int, error) {
	return 1, nil
}

func (m *mockDeploymentAttemptStore) ListByDeploymentID(
	ctx context.Context,
	deploymentID uuid.UUID,
	limit int,
	offset int,
) ([]model.DeploymentAttempt, error) {
	if m.listFunc != nil {
		return m.listFunc(ctx, deploymentID, limit, offset)
	}

	return []model.DeploymentAttempt{}, nil
}

func testDeploymentAttempt(
	deploymentID uuid.UUID,
) model.DeploymentAttempt {
	now := time.Now().UTC()
	completedAt := now.Add(2 * time.Second)
	durationMs := int64(2000)

	return model.DeploymentAttempt{
		ID:            uuid.New(),
		DeploymentID:  deploymentID,
		AttemptNumber: 1,
		Status:        model.AttemptStatusSucceeded,
		StartedAt:     now,
		CompletedAt:   &completedAt,
		DurationMs:    &durationMs,
		CreatedAt:     now,
	}
}

func TestListDeploymentAttempts(t *testing.T) {
	deploymentID := uuid.New()
	expectedAttempt := testDeploymentAttempt(deploymentID)

	manager := &mockDeploymentManager{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			deployment := testDeployment()
			deployment.ID = id
			return deployment, nil
		},
	}

	attemptStore := &mockDeploymentAttemptStore{
		listFunc: func(
			ctx context.Context,
			id uuid.UUID,
			limit int,
			offset int,
		) ([]model.DeploymentAttempt, error) {
			if id != deploymentID {
				t.Fatalf(
					"expected deployment ID %s, got %s",
					deploymentID,
					id,
				)
			}

			if limit != 10 {
				t.Fatalf("expected limit 10, got %d", limit)
			}

			if offset != 5 {
				t.Fatalf("expected offset 5, got %d", offset)
			}

			return []model.DeploymentAttempt{
				expectedAttempt,
			}, nil
		},
	}

	handler := NewDeploymentAttemptHandler(
		manager,
		attemptStore,
	)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/"+deploymentID.String()+
			"/attempts?limit=10&offset=5",
		nil,
	)

	request.SetPathValue("id", deploymentID.String())

	recorder := httptest.NewRecorder()

	handler.ListByDeploymentID(
		recorder,
		request,
	)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status 200, got %d",
			recorder.Code,
		)
	}

	responseBody := recorder.Body.String()

	if !strings.Contains(
		responseBody,
		expectedAttempt.ID.String(),
	) {
		t.Fatalf(
			"expected attempt ID in response, got %s",
			responseBody,
		)
	}

	if !strings.Contains(
		responseBody,
		`"limit":10`,
	) {
		t.Fatalf(
			"expected limit in response, got %s",
			responseBody,
		)
	}

	if !strings.Contains(
		responseBody,
		`"offset":5`,
	) {
		t.Fatalf(
			"expected offset in response, got %s",
			responseBody,
		)
	}
}

func TestListDeploymentAttemptsInvalidID(t *testing.T) {
	manager := &mockDeploymentManager{}
	attemptStore := &mockDeploymentAttemptStore{}

	handler := NewDeploymentAttemptHandler(
		manager,
		attemptStore,
	)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/invalid/attempts",
		nil,
	)

	request.SetPathValue("id", "invalid")

	recorder := httptest.NewRecorder()

	handler.ListByDeploymentID(
		recorder,
		request,
	)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status 400, got %d",
			recorder.Code,
		)
	}
}

func TestListDeploymentAttemptsDeploymentNotFound(t *testing.T) {
	deploymentID := uuid.New()

	manager := &mockDeploymentManager{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return model.Deployment{}, repository.ErrDeploymentNotFound
		},
	}

	attemptStore := &mockDeploymentAttemptStore{}

	handler := NewDeploymentAttemptHandler(
		manager,
		attemptStore,
	)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/"+deploymentID.String()+
			"/attempts",
		nil,
	)

	request.SetPathValue("id", deploymentID.String())

	recorder := httptest.NewRecorder()

	handler.ListByDeploymentID(
		recorder,
		request,
	)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf(
			"expected status 404, got %d",
			recorder.Code,
		)
	}
}

func TestListDeploymentAttemptsRepositoryError(t *testing.T) {
	deploymentID := uuid.New()

	manager := &mockDeploymentManager{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			deployment := testDeployment()
			deployment.ID = id
			return deployment, nil
		},
	}

	attemptStore := &mockDeploymentAttemptStore{
		listFunc: func(
			ctx context.Context,
			id uuid.UUID,
			limit int,
			offset int,
		) ([]model.DeploymentAttempt, error) {
			return nil, errors.New("database unavailable")
		},
	}

	handler := NewDeploymentAttemptHandler(
		manager,
		attemptStore,
	)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/"+deploymentID.String()+
			"/attempts",
		nil,
	)

	request.SetPathValue("id", deploymentID.String())

	recorder := httptest.NewRecorder()

	handler.ListByDeploymentID(
		recorder,
		request,
	)

	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf(
			"expected status 500, got %d",
			recorder.Code,
		)
	}
}

func TestListDeploymentAttemptsDefaultPagination(t *testing.T) {
	deploymentID := uuid.New()

	manager := &mockDeploymentManager{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			deployment := testDeployment()
			deployment.ID = id
			return deployment, nil
		},
	}

	attemptStore := &mockDeploymentAttemptStore{
		listFunc: func(
			ctx context.Context,
			id uuid.UUID,
			limit int,
			offset int,
		) ([]model.DeploymentAttempt, error) {
			if limit != 20 {
				t.Fatalf("expected default limit 20, got %d", limit)
			}

			if offset != 0 {
				t.Fatalf("expected default offset 0, got %d", offset)
			}

			return []model.DeploymentAttempt{}, nil
		},
	}

	handler := NewDeploymentAttemptHandler(
		manager,
		attemptStore,
	)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/deployments/"+deploymentID.String()+
			"/attempts",
		nil,
	)

	request.SetPathValue("id", deploymentID.String())

	recorder := httptest.NewRecorder()

	handler.ListByDeploymentID(
		recorder,
		request,
	)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status 200, got %d",
			recorder.Code,
		)
	}
}
