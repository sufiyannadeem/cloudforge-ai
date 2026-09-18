package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/repository"
)

type fakeProjectRepository struct {
	createdProject *model.Project
	projects       []model.Project

	createErr error
	getErr    error
	listErr   error
	updateErr error
	deleteErr error

	lastCreateInput model.CreateProjectInput
	lastLimit       int
	lastOffset      int
	lastUpdateInput model.UpdateProjectInput
	lastProjectID   uuid.UUID
}

func (f *fakeProjectRepository) Create(
	_ context.Context,
	input model.CreateProjectInput,
) (*model.Project, error) {
	f.lastCreateInput = input

	if f.createErr != nil {
		return nil, f.createErr
	}

	project := &model.Project{
		ID:            uuid.New(),
		Name:          input.Name,
		Description:   input.Description,
		RepositoryURL: input.RepositoryURL,
		DefaultBranch: input.DefaultBranch,
		Status:        model.ProjectStatusActive,
		CreatedAt:     time.Now(),
		UpdatedAt:     time.Now(),
	}

	f.createdProject = project

	return project, nil
}

func (f *fakeProjectRepository) GetByID(
	_ context.Context,
	id uuid.UUID,
) (*model.Project, error) {
	f.lastProjectID = id

	if f.getErr != nil {
		return nil, f.getErr
	}

	for _, project := range f.projects {
		if project.ID == id {
			projectCopy := project
			return &projectCopy, nil
		}
	}

	return nil, repository.ErrProjectNotFound
}

func (f *fakeProjectRepository) List(
	_ context.Context,
	limit, offset int,
) ([]model.Project, error) {
	f.lastLimit = limit
	f.lastOffset = offset

	if f.listErr != nil {
		return nil, f.listErr
	}

	return f.projects, nil
}

func (f *fakeProjectRepository) Update(
	_ context.Context,
	id uuid.UUID,
	input model.UpdateProjectInput,
) (*model.Project, error) {
	f.lastProjectID = id
	f.lastUpdateInput = input

	if f.updateErr != nil {
		return nil, f.updateErr
	}

	project := &model.Project{
		ID:            id,
		Name:          "updated-project",
		RepositoryURL: "https://github.com/example/updated-project",
		DefaultBranch: "main",
		Status:        model.ProjectStatusActive,
		CreatedAt:     time.Now(),
		UpdatedAt:     time.Now(),
	}

	return project, nil
}

func (f *fakeProjectRepository) Delete(
	_ context.Context,
	id uuid.UUID,
) error {
	f.lastProjectID = id

	return f.deleteErr
}

func TestProjectServiceCreateValidProject(t *testing.T) {
	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	description := "A platform engineering project"

	input := model.CreateProjectInput{
		Name:          "  CloudForge AI  ",
		Description:   &description,
		RepositoryURL: " https://github.com/example/cloudforge-ai ",
	}

	project, err := projectService.Create(context.Background(), input)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if project == nil {
		t.Fatal("expected project, got nil")
	}

	if fakeRepository.lastCreateInput.Name != "CloudForge AI" {
		t.Errorf(
			"expected trimmed name %q, got %q",
			"CloudForge AI",
			fakeRepository.lastCreateInput.Name,
		)
	}

	if fakeRepository.lastCreateInput.RepositoryURL !=
		"https://github.com/example/cloudforge-ai" {
		t.Errorf(
			"repository URL was not trimmed correctly: %q",
			fakeRepository.lastCreateInput.RepositoryURL,
		)
	}

	if fakeRepository.lastCreateInput.DefaultBranch != "main" {
		t.Errorf(
			"expected default branch %q, got %q",
			"main",
			fakeRepository.lastCreateInput.DefaultBranch,
		)
	}
}

func TestProjectServiceCreateRejectsInvalidName(t *testing.T) {
	tests := []struct {
		name        string
		projectName string
	}{
		{
			name:        "empty name",
			projectName: "",
		},
		{
			name:        "whitespace name",
			projectName: "     ",
		},
		{
			name:        "name longer than 100 characters",
			projectName: string(make([]byte, 101)),
		},
	}

	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			fakeRepository := &fakeProjectRepository{}
			projectService := NewProjectService(fakeRepository)

			input := model.CreateProjectInput{
				Name:          testCase.projectName,
				RepositoryURL: "https://github.com/example/project",
			}

			_, err := projectService.Create(context.Background(), input)

			if !errors.Is(err, ErrInvalidProjectName) {
				t.Fatalf(
					"expected ErrInvalidProjectName, got %v",
					err,
				)
			}
		})
	}
}

func TestProjectServiceCreateRejectsInvalidRepositoryURL(t *testing.T) {
	invalidURLs := []string{
		"",
		"example.com/project",
		"ftp://github.com/example/project",
		"not-a-url",
		"http://",
	}

	for _, invalidURL := range invalidURLs {
		t.Run(invalidURL, func(t *testing.T) {
			fakeRepository := &fakeProjectRepository{}
			projectService := NewProjectService(fakeRepository)

			input := model.CreateProjectInput{
				Name:          "CloudForge",
				RepositoryURL: invalidURL,
			}

			_, err := projectService.Create(context.Background(), input)

			if !errors.Is(err, ErrInvalidRepositoryURL) {
				t.Fatalf(
					"expected ErrInvalidRepositoryURL, got %v",
					err,
				)
			}
		})
	}
}

func TestProjectServiceCreateRejectsInvalidBranch(t *testing.T) {
	invalidBranches := []string{
		"branch with spaces",
		"branch\nnewline",
		string(make([]byte, 101)),
	}

	for _, branch := range invalidBranches {
		t.Run(branch, func(t *testing.T) {
			fakeRepository := &fakeProjectRepository{}
			projectService := NewProjectService(fakeRepository)

			input := model.CreateProjectInput{
				Name:          "CloudForge",
				RepositoryURL: "https://github.com/example/project",
				DefaultBranch: branch,
			}

			_, err := projectService.Create(context.Background(), input)

			if !errors.Is(err, ErrInvalidDefaultBranch) {
				t.Fatalf(
					"expected ErrInvalidDefaultBranch, got %v",
					err,
				)
			}
		})
	}
}

func TestProjectServiceCreatePropagatesRepositoryError(t *testing.T) {
	expectedError := errors.New("database unavailable")

	fakeRepository := &fakeProjectRepository{
		createErr: expectedError,
	}

	projectService := NewProjectService(fakeRepository)

	input := model.CreateProjectInput{
		Name:          "CloudForge",
		RepositoryURL: "https://github.com/example/project",
	}

	_, err := projectService.Create(context.Background(), input)

	if !errors.Is(err, expectedError) {
		t.Fatalf(
			"expected repository error %v, got %v",
			expectedError,
			err,
		)
	}
}

func TestProjectServiceListUsesDefaultLimit(t *testing.T) {
	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	_, err := projectService.List(context.Background(), 0, 0)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if fakeRepository.lastLimit != DefaultPageLimit {
		t.Errorf(
			"expected limit %d, got %d",
			DefaultPageLimit,
			fakeRepository.lastLimit,
		)
	}

	if fakeRepository.lastOffset != 0 {
		t.Errorf(
			"expected offset 0, got %d",
			fakeRepository.lastOffset,
		)
	}
}

func TestProjectServiceListRejectsInvalidPagination(t *testing.T) {
	tests := []struct {
		name   string
		limit  int
		offset int
	}{
		{
			name:   "negative limit",
			limit:  -1,
			offset: 0,
		},
		{
			name:   "limit above maximum",
			limit:  MaxPageLimit + 1,
			offset: 0,
		},
		{
			name:   "negative offset",
			limit:  20,
			offset: -1,
		},
	}

	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			fakeRepository := &fakeProjectRepository{}
			projectService := NewProjectService(fakeRepository)

			_, err := projectService.List(
				context.Background(),
				testCase.limit,
				testCase.offset,
			)

			if !errors.Is(err, ErrInvalidPagination) {
				t.Fatalf(
					"expected ErrInvalidPagination, got %v",
					err,
				)
			}
		})
	}
}

func TestProjectServiceGetByID(t *testing.T) {
	projectID := uuid.New()

	fakeRepository := &fakeProjectRepository{
		projects: []model.Project{
			{
				ID:            projectID,
				Name:          "CloudForge",
				RepositoryURL: "https://github.com/example/project",
				DefaultBranch: "main",
				Status:        model.ProjectStatusActive,
			},
		},
	}

	projectService := NewProjectService(fakeRepository)

	project, err := projectService.GetByID(
		context.Background(),
		projectID,
	)

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if project == nil {
		t.Fatal("expected project, got nil")
	}

	if project.ID != projectID {
		t.Errorf(
			"expected project ID %s, got %s",
			projectID,
			project.ID,
		)
	}
}

func TestProjectServiceGetByIDRejectsNilUUID(t *testing.T) {
	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	_, err := projectService.GetByID(
		context.Background(),
		uuid.Nil,
	)

	if !errors.Is(err, repository.ErrProjectNotFound) {
		t.Fatalf(
			"expected ErrProjectNotFound, got %v",
			err,
		)
	}
}

func TestProjectServiceUpdateValidInput(t *testing.T) {
	projectID := uuid.New()
	projectName := " Updated CloudForge "
	repositoryURL := " https://github.com/example/updated "
	branch := " develop "
	status := model.ProjectStatusInactive

	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	input := model.UpdateProjectInput{
		Name:          &projectName,
		RepositoryURL: &repositoryURL,
		DefaultBranch: &branch,
		Status:        &status,
	}

	_, err := projectService.Update(
		context.Background(),
		projectID,
		input,
	)

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if *fakeRepository.lastUpdateInput.Name != "Updated CloudForge" {
		t.Errorf(
			"expected trimmed name, got %q",
			*fakeRepository.lastUpdateInput.Name,
		)
	}

	if *fakeRepository.lastUpdateInput.RepositoryURL !=
		"https://github.com/example/updated" {
		t.Errorf(
			"expected trimmed URL, got %q",
			*fakeRepository.lastUpdateInput.RepositoryURL,
		)
	}

	if *fakeRepository.lastUpdateInput.DefaultBranch != "develop" {
		t.Errorf(
			"expected trimmed branch, got %q",
			*fakeRepository.lastUpdateInput.DefaultBranch,
		)
	}
}

func TestProjectServiceUpdateRejectsInvalidStatus(t *testing.T) {
	projectID := uuid.New()
	invalidStatus := model.ProjectStatus("unknown")

	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	input := model.UpdateProjectInput{
		Status: &invalidStatus,
	}

	_, err := projectService.Update(
		context.Background(),
		projectID,
		input,
	)

	if !errors.Is(err, ErrInvalidProjectStatus) {
		t.Fatalf(
			"expected ErrInvalidProjectStatus, got %v",
			err,
		)
	}
}

func TestProjectServiceUpdateRejectsNilUUID(t *testing.T) {
	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	_, err := projectService.Update(
		context.Background(),
		uuid.Nil,
		model.UpdateProjectInput{},
	)

	if !errors.Is(err, repository.ErrProjectNotFound) {
		t.Fatalf(
			"expected ErrProjectNotFound, got %v",
			err,
		)
	}
}

func TestProjectServiceDelete(t *testing.T) {
	projectID := uuid.New()

	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	err := projectService.Delete(
		context.Background(),
		projectID,
	)

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if fakeRepository.lastProjectID != projectID {
		t.Errorf(
			"expected project ID %s, got %s",
			projectID,
			fakeRepository.lastProjectID,
		)
	}
}

func TestProjectServiceDeleteRejectsNilUUID(t *testing.T) {
	fakeRepository := &fakeProjectRepository{}
	projectService := NewProjectService(fakeRepository)

	err := projectService.Delete(
		context.Background(),
		uuid.Nil,
	)

	if !errors.Is(err, repository.ErrProjectNotFound) {
		t.Fatalf(
			"expected ErrProjectNotFound, got %v",
			err,
		)
	}
}

func TestProjectServiceDeletePropagatesRepositoryError(t *testing.T) {
	expectedError := errors.New("delete failed")

	fakeRepository := &fakeProjectRepository{
		deleteErr: expectedError,
	}

	projectService := NewProjectService(fakeRepository)

	err := projectService.Delete(
		context.Background(),
		uuid.New(),
	)

	if !errors.Is(err, expectedError) {
		t.Fatalf(
			"expected repository error %v, got %v",
			expectedError,
			err,
		)
	}
}
