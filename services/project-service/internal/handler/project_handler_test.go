package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/service"
)

type fakeProjectService struct {
	projects []model.Project

	createFunc func(
		ctx context.Context,
		input model.CreateProjectInput,
	) (*model.Project, error)

	getByIDFunc func(
		ctx context.Context,
		id uuid.UUID,
	) (*model.Project, error)

	listFunc func(
		ctx context.Context,
		limit int,
		offset int,
	) ([]model.Project, error)

	updateFunc func(
		ctx context.Context,
		id uuid.UUID,
		input model.UpdateProjectInput,
	) (*model.Project, error)

	deleteFunc func(
		ctx context.Context,
		id uuid.UUID,
	) error
}

func (f *fakeProjectService) Create(
	ctx context.Context,
	input model.CreateProjectInput,
) (*model.Project, error) {
	if f.createFunc != nil {
		return f.createFunc(ctx, input)
	}

	project := model.Project{
		ID:            uuid.New(),
		Name:          input.Name,
		Description:   input.Description,
		RepositoryURL: input.RepositoryURL,
		DefaultBranch: input.DefaultBranch,
		Status:        model.ProjectStatusActive,
	}

	f.projects = append(f.projects, project)

	return &project, nil
}

func (f *fakeProjectService) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (*model.Project, error) {
	if f.getByIDFunc != nil {
		return f.getByIDFunc(ctx, id)
	}

	for _, project := range f.projects {
		if project.ID == id {
			return &project, nil
		}
	}

	return nil, repository.ErrProjectNotFound
}

func (f *fakeProjectService) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.Project, error) {
	if f.listFunc != nil {
		return f.listFunc(ctx, limit, offset)
	}

	return f.projects, nil
}

func (f *fakeProjectService) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateProjectInput,
) (*model.Project, error) {
	if f.updateFunc != nil {
		return f.updateFunc(ctx, id, input)
	}

	return nil, repository.ErrProjectNotFound
}

func (f *fakeProjectService) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if f.deleteFunc != nil {
		return f.deleteFunc(ctx, id)
	}

	return repository.ErrProjectNotFound
}

func newTestHandler(
	fakeService *fakeProjectService,
) http.Handler {
	return NewProjectHandler(fakeService)
}

func decodeResponse(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	target any,
) {
	t.Helper()

	if err := json.NewDecoder(recorder.Body).Decode(target); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
}

func TestCreateProjectSuccess(t *testing.T) {
	fakeService := &fakeProjectService{
		createFunc: func(
			ctx context.Context,
			input model.CreateProjectInput,
		) (*model.Project, error) {
			description := "Test project"

			return &model.Project{
				ID:            uuid.New(),
				Name:          input.Name,
				Description:   &description,
				RepositoryURL: input.RepositoryURL,
				DefaultBranch: "main",
				Status:        model.ProjectStatusActive,
			}, nil
		},
	}

	handler := newTestHandler(fakeService)

	body := `{
		"name": "CloudForge Test",
		"description": "Test project",
		"repository_url": "https://github.com/example/test",
		"default_branch": "main"
	}`

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

	var response model.Project
	decodeResponse(t, recorder, &response)

	if response.Name != "CloudForge Test" {
		t.Fatalf("expected project name, got %q", response.Name)
	}

	if response.RepositoryURL != "https://github.com/example/test" {
		t.Fatalf("unexpected repository URL: %q", response.RepositoryURL)
	}
}

func TestCreateProjectInvalidJSON(t *testing.T) {
	fakeService := &fakeProjectService{}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodPost,
		"/projects",
		strings.NewReader(`{"name":`),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusBadRequest,
			recorder.Code,
		)
	}
}

func TestCreateProjectUnknownJSONField(t *testing.T) {
	fakeService := &fakeProjectService{}

	handler := newTestHandler(fakeService)

	body := `{
		"name": "CloudForge Test",
		"repository_url": "https://github.com/example/test",
		"unexpected_field": "not allowed"
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
			"expected status %d, got %d",
			http.StatusBadRequest,
			recorder.Code,
		)
	}
}

func TestGetProjectByIDSuccess(t *testing.T) {
	projectID := uuid.New()

	fakeService := &fakeProjectService{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (*model.Project, error) {
			return &model.Project{
				ID:            projectID,
				Name:          "CloudForge Test",
				RepositoryURL: "https://github.com/example/test",
				DefaultBranch: "main",
				Status:        model.ProjectStatusActive,
			}, nil
		},
	}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodGet,
		"/projects/"+projectID.String(),
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusOK,
			recorder.Code,
		)
	}

	var response model.Project
	decodeResponse(t, recorder, &response)

	if response.ID != projectID {
		t.Fatalf(
			"expected project ID %s, got %s",
			projectID,
			response.ID,
		)
	}
}

func TestGetProjectByIDInvalidUUID(t *testing.T) {
	fakeService := &fakeProjectService{}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodGet,
		"/projects/not-a-valid-uuid",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusBadRequest,
			recorder.Code,
		)
	}
}

func TestGetProjectNotFound(t *testing.T) {
	projectID := uuid.New()

	fakeService := &fakeProjectService{
		getByIDFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) (*model.Project, error) {
			return nil, repository.ErrProjectNotFound
		},
	}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodGet,
		"/projects/"+projectID.String(),
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusNotFound,
			recorder.Code,
		)
	}

	var response map[string]string
	decodeResponse(t, recorder, &response)

	if response["error"] != "project not found" {
		t.Fatalf(
			"expected project not found error, got %q",
			response["error"],
		)
	}
}

func TestListProjectsSuccess(t *testing.T) {
	projectID := uuid.New()

	fakeService := &fakeProjectService{
		listFunc: func(
			ctx context.Context,
			limit int,
			offset int,
		) ([]model.Project, error) {
			return []model.Project{
				{
					ID:            projectID,
					Name:          "CloudForge Test",
					RepositoryURL: "https://github.com/example/test",
					DefaultBranch: "main",
					Status:        model.ProjectStatusActive,
				},
			}, nil
		},
	}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodGet,
		"/projects?limit=10&offset=0",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusOK,
			recorder.Code,
		)
	}

	var response struct {
		Data []model.Project `json:"data"`
	}

	decodeResponse(t, recorder, &response)

	if len(response.Data) != 1 {
		t.Fatalf(
			"expected 1 project, got %d",
			len(response.Data),
		)
	}

	if response.Data[0].ID != projectID {
		t.Fatalf("unexpected project ID: %s", response.Data[0].ID)
	}
}

func TestListProjectsInvalidLimit(t *testing.T) {
	fakeService := &fakeProjectService{
		listFunc: func(
			ctx context.Context,
			limit int,
			offset int,
		) ([]model.Project, error) {
			return nil, service.ErrInvalidPagination
		},
	}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodGet,
		"/projects?limit=1000",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusBadRequest,
			recorder.Code,
		)
	}
}

func TestUpdateProjectSuccess(t *testing.T) {
	projectID := uuid.New()

	fakeService := &fakeProjectService{
		updateFunc: func(
			ctx context.Context,
			id uuid.UUID,
			input model.UpdateProjectInput,
		) (*model.Project, error) {
			description := "Updated description"

			return &model.Project{
				ID:            projectID,
				Name:          "CloudForge Updated",
				Description:   &description,
				RepositoryURL: "https://github.com/example/test",
				DefaultBranch: "develop",
				Status:        model.ProjectStatusActive,
			}, nil
		},
	}

	handler := newTestHandler(fakeService)

	body := `{
		"name": "CloudForge Updated",
		"description": "Updated description",
		"default_branch": "develop"
	}`

	request := httptest.NewRequest(
		http.MethodPatch,
		"/projects/"+projectID.String(),
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status %d, got %d; body: %s",
			http.StatusOK,
			recorder.Code,
			recorder.Body.String(),
		)
	}

	var response model.Project
	decodeResponse(t, recorder, &response)

	if response.DefaultBranch != "develop" {
		t.Fatalf(
			"expected branch develop, got %q",
			response.DefaultBranch,
		)
	}
}

func TestDeleteProjectSuccess(t *testing.T) {
	projectID := uuid.New()

	deleteCalled := false

	fakeService := &fakeProjectService{
		deleteFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) error {
			deleteCalled = true

			if id != projectID {
				t.Fatalf(
					"expected ID %s, got %s",
					projectID,
					id,
				)
			}

			return nil
		},
	}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodDelete,
		"/projects/"+projectID.String(),
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNoContent {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusNoContent,
			recorder.Code,
		)
	}

	if !deleteCalled {
		t.Fatal("expected delete service method to be called")
	}

	if recorder.Body.Len() != 0 {
		t.Fatalf(
			"expected empty response body, got %q",
			recorder.Body.String(),
		)
	}
}

func TestDeleteProjectNotFound(t *testing.T) {
	projectID := uuid.New()

	fakeService := &fakeProjectService{
		deleteFunc: func(
			ctx context.Context,
			id uuid.UUID,
		) error {
			return repository.ErrProjectNotFound
		},
	}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodDelete,
		"/projects/"+projectID.String(),
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusNotFound,
			recorder.Code,
		)
	}
}

func TestProjectByIDUnsupportedMethod(t *testing.T) {
	projectID := uuid.New()

	fakeService := &fakeProjectService{}

	handler := newTestHandler(fakeService)

	request := httptest.NewRequest(
		http.MethodPut,
		"/projects/"+projectID.String(),
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusMethodNotAllowed {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusMethodNotAllowed,
			recorder.Code,
		)
	}
}

func TestCreateProjectServiceError(t *testing.T) {
	fakeService := &fakeProjectService{
		createFunc: func(
			ctx context.Context,
			input model.CreateProjectInput,
		) (*model.Project, error) {
			return nil, errors.New("database unavailable")
		},
	}

	handler := newTestHandler(fakeService)

	body := `{
		"name": "CloudForge Test",
		"repository_url": "https://github.com/example/test"
	}`

	request := httptest.NewRequest(
		http.MethodPost,
		"/projects",
		strings.NewReader(body),
	)

	request.Header.Set("Content-Type", "application/json")

	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf(
			"expected status %d, got %d",
			http.StatusInternalServerError,
			recorder.Code,
		)
	}
}
