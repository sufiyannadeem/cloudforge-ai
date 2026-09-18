package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
)

type mockDeploymentStore struct {
	createFunc  func(context.Context, model.Deployment) error
	getByIDFunc func(context.Context, uuid.UUID) (model.Deployment, error)
	listFunc    func(context.Context, int, int) ([]model.Deployment, error)
	updateFunc  func(context.Context, model.Deployment) error
	deleteFunc  func(context.Context, uuid.UUID) error

	createdDeployment model.Deployment
	updatedDeployment model.Deployment
	listLimit         int
	listOffset        int
}

func (m *mockDeploymentStore) Create(
	ctx context.Context,
	deployment model.Deployment,
) error {
	m.createdDeployment = deployment

	if m.createFunc != nil {
		return m.createFunc(ctx, deployment)
	}

	return nil
}

func (m *mockDeploymentStore) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.Deployment, error) {
	if m.getByIDFunc != nil {
		return m.getByIDFunc(ctx, id)
	}

	return model.Deployment{}, nil
}

func (m *mockDeploymentStore) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.Deployment, error) {
	m.listLimit = limit
	m.listOffset = offset

	if m.listFunc != nil {
		return m.listFunc(ctx, limit, offset)
	}

	return []model.Deployment{}, nil
}

func (m *mockDeploymentStore) Update(
	ctx context.Context,
	deployment model.Deployment,
) error {
	m.updatedDeployment = deployment

	if m.updateFunc != nil {
		return m.updateFunc(ctx, deployment)
	}

	return nil
}

func (m *mockDeploymentStore) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if m.deleteFunc != nil {
		return m.deleteFunc(ctx, id)
	}

	return nil
}

func validCreateInput() model.CreateDeploymentInput {
	return model.CreateDeploymentInput{
		ProjectID:    uuid.New(),
		Environment:  "production",
		Image:        "nginx:1.27",
		GitCommitSHA: "abcdef1234567",
		Namespace:    "production",
	}
}

func existingDeployment() model.Deployment {
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

func TestCreateDeploymentSuccess(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	input := validCreateInput()

	deployment, err := svc.Create(context.Background(), input)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if deployment.ID == uuid.Nil {
		t.Fatal("expected deployment ID to be generated")
	}

	if deployment.ProjectID != input.ProjectID {
		t.Fatalf("expected project ID %s, got %s",
			input.ProjectID,
			deployment.ProjectID,
		)
	}

	if deployment.Environment != input.Environment {
		t.Fatalf("expected environment %s, got %s",
			input.Environment,
			deployment.Environment,
		)
	}

	if deployment.Status != model.DeploymentStatusPending {
		t.Fatalf("expected pending status, got %s", deployment.Status)
	}

	if store.createdDeployment.ID != deployment.ID {
		t.Fatal("expected created deployment to be passed to repository")
	}
}

func TestCreateDeploymentRejectsMissingProjectID(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	input := validCreateInput()
	input.ProjectID = uuid.Nil

	_, err := svc.Create(context.Background(), input)

	if !errors.Is(err, ErrInvalidProjectID) {
		t.Fatalf("expected ErrInvalidProjectID, got %v", err)
	}
}

func TestCreateDeploymentRejectsInvalidEnvironment(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	input := validCreateInput()
	input.Environment = "testing"

	_, err := svc.Create(context.Background(), input)

	if !errors.Is(err, ErrInvalidEnvironment) {
		t.Fatalf("expected ErrInvalidEnvironment, got %v", err)
	}
}

func TestCreateDeploymentRejectsMissingImage(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	input := validCreateInput()
	input.Image = "   "

	_, err := svc.Create(context.Background(), input)

	if !errors.Is(err, ErrInvalidImage) {
		t.Fatalf("expected ErrInvalidImage, got %v", err)
	}
}

func TestCreateDeploymentRejectsMissingGitCommitSHA(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	input := validCreateInput()
	input.GitCommitSHA = "   "

	_, err := svc.Create(context.Background(), input)

	if !errors.Is(err, ErrInvalidGitCommitSHA) {
		t.Fatalf("expected ErrInvalidGitCommitSHA, got %v", err)
	}
}

func TestCreateDeploymentRejectsMissingNamespace(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	input := validCreateInput()
	input.Namespace = "   "

	_, err := svc.Create(context.Background(), input)

	if !errors.Is(err, ErrInvalidNamespace) {
		t.Fatalf("expected ErrInvalidNamespace, got %v", err)
	}
}

func TestGetDeploymentRejectsNilID(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	_, err := svc.GetByID(context.Background(), uuid.Nil)

	if !errors.Is(err, ErrInvalidDeploymentID) {
		t.Fatalf("expected ErrInvalidDeploymentID, got %v", err)
	}
}

func TestGetDeploymentSuccess(t *testing.T) {
	expected := existingDeployment()

	store := &mockDeploymentStore{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return expected, nil
		},
	}

	svc := NewDeploymentService(store)

	actual, err := svc.GetByID(context.Background(), expected.ID)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if actual.ID != expected.ID {
		t.Fatalf("expected ID %s, got %s", expected.ID, actual.ID)
	}
}

func TestGetDeploymentNotFound(t *testing.T) {
	store := &mockDeploymentStore{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return model.Deployment{}, repository.ErrDeploymentNotFound
		},
	}

	svc := NewDeploymentService(store)

	_, err := svc.GetByID(context.Background(), uuid.New())

	if !errors.Is(err, repository.ErrDeploymentNotFound) {
		t.Fatalf("expected ErrDeploymentNotFound, got %v", err)
	}
}

func TestListDeploymentsUsesDefaultLimit(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	_, err := svc.List(context.Background(), 0, -10)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if store.listLimit != 20 {
		t.Fatalf("expected default limit 20, got %d", store.listLimit)
	}

	if store.listOffset != 0 {
		t.Fatalf("expected default offset 0, got %d", store.listOffset)
	}
}

func TestListDeploymentsCapsMaximumLimit(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	_, err := svc.List(context.Background(), 500, 10)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if store.listLimit != 100 {
		t.Fatalf("expected maximum limit 100, got %d", store.listLimit)
	}

	if store.listOffset != 10 {
		t.Fatalf("expected offset 10, got %d", store.listOffset)
	}
}

func TestUpdateDeploymentSuccess(t *testing.T) {
	existing := existingDeployment()

	newImage := "nginx:1.28"
	newStatus := model.DeploymentStatusRunning

	store := &mockDeploymentStore{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return existing, nil
		},
	}

	svc := NewDeploymentService(store)

	updated, err := svc.Update(
		context.Background(),
		existing.ID,
		model.UpdateDeploymentInput{
			Image:  &newImage,
			Status: &newStatus,
		},
	)

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if updated.Image != newImage {
		t.Fatalf("expected image %s, got %s", newImage, updated.Image)
	}

	if updated.Status != newStatus {
		t.Fatalf("expected status %s, got %s", newStatus, updated.Status)
	}

	if !updated.UpdatedAt.After(existing.UpdatedAt) ||
		updated.UpdatedAt.Equal(existing.UpdatedAt) {
		t.Fatal("expected UpdatedAt to change")
	}

	if store.updatedDeployment.Image != newImage {
		t.Fatal("expected updated deployment to be passed to repository")
	}
}

func TestUpdateDeploymentRejectsInvalidStatus(t *testing.T) {
	existing := existingDeployment()
	invalidStatus := model.DeploymentStatus("invalid")

	store := &mockDeploymentStore{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (model.Deployment, error) {
			return existing, nil
		},
	}

	svc := NewDeploymentService(store)

	_, err := svc.Update(
		context.Background(),
		existing.ID,
		model.UpdateDeploymentInput{
			Status: &invalidStatus,
		},
	)

	if !errors.Is(err, ErrInvalidDeploymentStatus) {
		t.Fatalf("expected ErrInvalidDeploymentStatus, got %v", err)
	}
}

func TestUpdateDeploymentRejectsNilID(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	_, err := svc.Update(
		context.Background(),
		uuid.Nil,
		model.UpdateDeploymentInput{},
	)

	if !errors.Is(err, ErrInvalidDeploymentID) {
		t.Fatalf("expected ErrInvalidDeploymentID, got %v", err)
	}
}

func TestDeleteDeploymentSuccess(t *testing.T) {
	deploymentID := uuid.New()
	store := &mockDeploymentStore{}

	svc := NewDeploymentService(store)

	err := svc.Delete(context.Background(), deploymentID)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestDeleteDeploymentRejectsNilID(t *testing.T) {
	store := &mockDeploymentStore{}
	svc := NewDeploymentService(store)

	err := svc.Delete(context.Background(), uuid.Nil)

	if !errors.Is(err, ErrInvalidDeploymentID) {
		t.Fatalf("expected ErrInvalidDeploymentID, got %v", err)
	}
}
