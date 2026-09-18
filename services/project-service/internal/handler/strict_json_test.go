package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/repository"
)

type strictJSONTestService struct {
	createCalled bool
	updateCalled bool
}

func (f *strictJSONTestService) Create(
	ctx context.Context,
	input model.CreateProjectInput,
) (*model.Project, error) {
	f.createCalled = true

	return &model.Project{
		ID:            uuid.New(),
		Name:          input.Name,
		Description:   input.Description,
		RepositoryURL: input.RepositoryURL,
		DefaultBranch: input.DefaultBranch,
		Status:        model.ProjectStatusActive,
	}, nil
}

func (f *strictJSONTestService) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (*model.Project, error) {
	return nil, repository.ErrProjectNotFound
}

func (f *strictJSONTestService) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.Project, error) {
	return []model.Project{}, nil
}

func (f *strictJSONTestService) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateProjectInput,
) (*model.Project, error) {
	f.updateCalled = true

	return &model.Project{
		ID:            id,
		Name:          "Updated Project",
		RepositoryURL: "https://github.com/example/test",
		DefaultBranch: "main",
		Status:        model.ProjectStatusActive,
	}, nil
}

func (f *strictJSONTestService) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	return repository.ErrProjectNotFound
}

func TestCreateProjectRejectsMultipleJSONObjects(t *testing.T) {
	fakeService := &strictJSONTestService{}
	handler := NewProjectHandler(fakeService)

	body := `{
		"name": "CloudForge Test",
		"repository_url": "https://github.com/example/test"
	} {
		"name": "Second Project",
		"repository_url": "https://github.com/example/second"
	}`

	request := httptest.NewRequest(
		http.MethodPost,
		"/projects",
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status %d, got %d; body: %s",
			http.StatusBadRequest,
			recorder.Code,
			recorder.Body.String(),
		)
	}

	if fakeService.createCalled {
		t.Fatal("service should not be called when multiple JSON objects are provided")
	}
}

func TestCreateProjectRejectsTrailingGarbage(t *testing.T) {
	fakeService := &strictJSONTestService{}
	handler := NewProjectHandler(fakeService)

	body := `{
		"name": "CloudForge Test",
		"repository_url": "https://github.com/example/test"
	} trailing-garbage`

	request := httptest.NewRequest(
		http.MethodPost,
		"/projects",
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status %d, got %d; body: %s",
			http.StatusBadRequest,
			recorder.Code,
			recorder.Body.String(),
		)
	}

	if fakeService.createCalled {
		t.Fatal("service should not be called when trailing garbage is provided")
	}
}

func TestCreateProjectAllowsTrailingWhitespace(t *testing.T) {
	fakeService := &strictJSONTestService{}
	handler := NewProjectHandler(fakeService)

	body := `{
		"name": "CloudForge Test",
		"repository_url": "https://github.com/example/test"
	}    

`

	request := httptest.NewRequest(
		http.MethodPost,
		"/projects",
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusCreated {
		t.Fatalf(
			"expected status %d, got %d; body: %s",
			http.StatusCreated,
			recorder.Code,
			recorder.Body.String(),
		)
	}

	if !fakeService.createCalled {
		t.Fatal("service should be called for valid JSON with trailing whitespace")
	}
}

func TestUpdateProjectRejectsMultipleJSONObjects(t *testing.T) {
	fakeService := &strictJSONTestService{}
	handler := NewProjectHandler(fakeService)

	projectID := uuid.New()

	body := `{
		"name": "Updated Project"
	} {
		"name": "Second Project"
	}`

	request := httptest.NewRequest(
		http.MethodPatch,
		"/projects/"+projectID.String(),
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status %d, got %d; body: %s",
			http.StatusBadRequest,
			recorder.Code,
			recorder.Body.String(),
		)
	}

	if fakeService.updateCalled {
		t.Fatal("service should not be called when multiple JSON objects are provided")
	}
}

func TestUpdateProjectRejectsTrailingGarbage(t *testing.T) {
	fakeService := &strictJSONTestService{}
	handler := NewProjectHandler(fakeService)

	projectID := uuid.New()

	body := `{
		"name": "Updated Project"
	} invalid-data`

	request := httptest.NewRequest(
		http.MethodPatch,
		"/projects/"+projectID.String(),
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status %d, got %d; body: %s",
			http.StatusBadRequest,
			recorder.Code,
			recorder.Body.String(),
		)
	}

	if fakeService.updateCalled {
		t.Fatal("service should not be called when trailing garbage is provided")
	}
}
