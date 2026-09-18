package service

import (
	"context"
	"errors"
	"net/url"
	"strings"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/repository"
)

const (
	DefaultPageLimit = 20
	MaxPageLimit     = 100
	MaxProjectName   = 100
	MaxBranchName    = 100
)

var (
	ErrInvalidProjectName   = errors.New("invalid project name")
	ErrInvalidRepositoryURL = errors.New("invalid repository URL")
	ErrInvalidDefaultBranch = errors.New("invalid default branch")
	ErrInvalidProjectStatus = errors.New("invalid project status")
	ErrInvalidPagination    = errors.New("invalid pagination")
)

type ProjectService interface {
	Create(ctx context.Context, input model.CreateProjectInput) (*model.Project, error)
	GetByID(ctx context.Context, id uuid.UUID) (*model.Project, error)
	List(ctx context.Context, limit, offset int) ([]model.Project, error)
	Update(ctx context.Context, id uuid.UUID, input model.UpdateProjectInput) (*model.Project, error)
	Delete(ctx context.Context, id uuid.UUID) error
}

type projectService struct {
	repository repository.ProjectRepository
}

func NewProjectService(
	projectRepository repository.ProjectRepository,
) ProjectService {
	return &projectService{
		repository: projectRepository,
	}
}

func (s *projectService) Create(
	ctx context.Context,
	input model.CreateProjectInput,
) (*model.Project, error) {
	normalizedInput, err := validateCreateInput(input)
	if err != nil {
		return nil, err
	}

	return s.repository.Create(ctx, normalizedInput)
}

func (s *projectService) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (*model.Project, error) {
	if id == uuid.Nil {
		return nil, repository.ErrProjectNotFound
	}

	return s.repository.GetByID(ctx, id)
}

func (s *projectService) List(
	ctx context.Context,
	limit, offset int,
) ([]model.Project, error) {
	normalizedLimit, normalizedOffset, err := validatePagination(limit, offset)
	if err != nil {
		return nil, err
	}

	return s.repository.List(ctx, normalizedLimit, normalizedOffset)
}

func (s *projectService) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateProjectInput,
) (*model.Project, error) {
	if id == uuid.Nil {
		return nil, repository.ErrProjectNotFound
	}

	normalizedInput, err := validateUpdateInput(input)
	if err != nil {
		return nil, err
	}

	return s.repository.Update(ctx, id, normalizedInput)
}

func (s *projectService) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if id == uuid.Nil {
		return repository.ErrProjectNotFound
	}

	return s.repository.Delete(ctx, id)
}

func validateCreateInput(
	input model.CreateProjectInput,
) (model.CreateProjectInput, error) {
	input.Name = strings.TrimSpace(input.Name)

	if input.Name == "" || len(input.Name) > MaxProjectName {
		return model.CreateProjectInput{}, ErrInvalidProjectName
	}

	if err := validateRepositoryURL(input.RepositoryURL); err != nil {
		return model.CreateProjectInput{}, err
	}

	input.RepositoryURL = strings.TrimSpace(input.RepositoryURL)

	if input.DefaultBranch == "" {
		input.DefaultBranch = "main"
	}

	input.DefaultBranch = strings.TrimSpace(input.DefaultBranch)

	if input.DefaultBranch == "" ||
		len(input.DefaultBranch) > MaxBranchName ||
		strings.ContainsAny(input.DefaultBranch, " \t\n\r") {
		return model.CreateProjectInput{}, ErrInvalidDefaultBranch
	}

	if input.Description != nil {
		description := strings.TrimSpace(*input.Description)
		input.Description = &description
	}

	return input, nil
}

func validateUpdateInput(
	input model.UpdateProjectInput,
) (model.UpdateProjectInput, error) {
	if input.Name != nil {
		name := strings.TrimSpace(*input.Name)

		if name == "" || len(name) > MaxProjectName {
			return model.UpdateProjectInput{}, ErrInvalidProjectName
		}

		input.Name = &name
	}

	if input.RepositoryURL != nil {
		repositoryURL := strings.TrimSpace(*input.RepositoryURL)

		if err := validateRepositoryURL(repositoryURL); err != nil {
			return model.UpdateProjectInput{}, err
		}

		input.RepositoryURL = &repositoryURL
	}

	if input.DefaultBranch != nil {
		branch := strings.TrimSpace(*input.DefaultBranch)

		if branch == "" ||
			len(branch) > MaxBranchName ||
			strings.ContainsAny(branch, " \t\n\r") {
			return model.UpdateProjectInput{}, ErrInvalidDefaultBranch
		}

		input.DefaultBranch = &branch
	}

	if input.Status != nil {
		if !isValidProjectStatus(*input.Status) {
			return model.UpdateProjectInput{}, ErrInvalidProjectStatus
		}
	}

	if input.Description != nil {
		description := strings.TrimSpace(*input.Description)
		input.Description = &description
	}

	return input, nil
}

func validateRepositoryURL(repositoryURL string) error {
	repositoryURL = strings.TrimSpace(repositoryURL)

	if repositoryURL == "" {
		return ErrInvalidRepositoryURL
	}

	parsedURL, err := url.ParseRequestURI(repositoryURL)
	if err != nil {
		return ErrInvalidRepositoryURL
	}

	if parsedURL.Scheme != "http" && parsedURL.Scheme != "https" {
		return ErrInvalidRepositoryURL
	}

	if parsedURL.Host == "" {
		return ErrInvalidRepositoryURL
	}

	return nil
}

func isValidProjectStatus(
	status model.ProjectStatus,
) bool {
	switch status {
	case model.ProjectStatusActive,
		model.ProjectStatusInactive,
		model.ProjectStatusArchived:
		return true
	default:
		return false
	}
}

func validatePagination(
	limit, offset int,
) (int, int, error) {
	if limit == 0 {
		limit = DefaultPageLimit
	}

	if limit < 1 || limit > MaxPageLimit {
		return 0, 0, ErrInvalidPagination
	}

	if offset < 0 {
		return 0, 0, ErrInvalidPagination
	}

	return limit, offset, nil
}
