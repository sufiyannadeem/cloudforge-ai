package repository

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
)

var ErrProjectNotFound = errors.New("project not found")

type ProjectRepository interface {
	Create(
		ctx context.Context,
		input model.CreateProjectInput,
	) (*model.Project, error)

	GetByID(
		ctx context.Context,
		id uuid.UUID,
	) (*model.Project, error)

	List(
		ctx context.Context,
		limit int,
		offset int,
	) ([]model.Project, error)

	Update(
		ctx context.Context,
		id uuid.UUID,
		input model.UpdateProjectInput,
	) (*model.Project, error)

	Delete(
		ctx context.Context,
		id uuid.UUID,
	) error
}

type projectRepository struct {
	db *pgxpool.Pool
}

func NewProjectRepository(db *pgxpool.Pool) ProjectRepository {
	return &projectRepository{
		db: db,
	}
}

func (r *projectRepository) Create(
	ctx context.Context,
	input model.CreateProjectInput,
) (*model.Project, error) {
	const query = `
		INSERT INTO projects (
			name,
			description,
			repository_url,
			default_branch
		)
		VALUES ($1, $2, $3, COALESCE(NULLIF($4, ''), 'main'))
		RETURNING
			id,
			name,
			description,
			repository_url,
			default_branch,
			status,
			created_at,
			updated_at
	`

	project := &model.Project{}

	err := r.db.QueryRow(
		ctx,
		query,
		input.Name,
		input.Description,
		input.RepositoryURL,
		input.DefaultBranch,
	).Scan(
		&project.ID,
		&project.Name,
		&project.Description,
		&project.RepositoryURL,
		&project.DefaultBranch,
		&project.Status,
		&project.CreatedAt,
		&project.UpdatedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("create project: %w", err)
	}

	return project, nil
}

func (r *projectRepository) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (*model.Project, error) {
	const query = `
		SELECT
			id,
			name,
			description,
			repository_url,
			default_branch,
			status,
			created_at,
			updated_at
		FROM projects
		WHERE id = $1
	`

	project := &model.Project{}

	err := r.db.QueryRow(ctx, query, id).Scan(
		&project.ID,
		&project.Name,
		&project.Description,
		&project.RepositoryURL,
		&project.DefaultBranch,
		&project.Status,
		&project.CreatedAt,
		&project.UpdatedAt,
	)

	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrProjectNotFound
	}

	if err != nil {
		return nil, fmt.Errorf("get project by ID: %w", err)
	}

	return project, nil
}

func (r *projectRepository) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.Project, error) {
	const query = `
		SELECT
			id,
			name,
			description,
			repository_url,
			default_branch,
			status,
			created_at,
			updated_at
		FROM projects
		ORDER BY created_at DESC
		LIMIT $1 OFFSET $2
	`

	rows, err := r.db.Query(ctx, query, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("list projects: %w", err)
	}
	defer rows.Close()

	projects := make([]model.Project, 0)

	for rows.Next() {
		var project model.Project

		err := rows.Scan(
			&project.ID,
			&project.Name,
			&project.Description,
			&project.RepositoryURL,
			&project.DefaultBranch,
			&project.Status,
			&project.CreatedAt,
			&project.UpdatedAt,
		)

		if err != nil {
			return nil, fmt.Errorf("scan project: %w", err)
		}

		projects = append(projects, project)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate projects: %w", err)
	}

	return projects, nil
}

func (r *projectRepository) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateProjectInput,
) (*model.Project, error) {
	const query = `
		UPDATE projects
		SET
			name = COALESCE($2, name),
			description = COALESCE($3, description),
			repository_url = COALESCE($4, repository_url),
			default_branch = COALESCE($5, default_branch),
			status = COALESCE($6, status),
			updated_at = NOW()
		WHERE id = $1
		RETURNING
			id,
			name,
			description,
			repository_url,
			default_branch,
			status,
			created_at,
			updated_at
	`

	project := &model.Project{}

	err := r.db.QueryRow(
		ctx,
		query,
		id,
		input.Name,
		input.Description,
		input.RepositoryURL,
		input.DefaultBranch,
		input.Status,
	).Scan(
		&project.ID,
		&project.Name,
		&project.Description,
		&project.RepositoryURL,
		&project.DefaultBranch,
		&project.Status,
		&project.CreatedAt,
		&project.UpdatedAt,
	)

	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrProjectNotFound
	}

	if err != nil {
		return nil, fmt.Errorf("update project: %w", err)
	}

	return project, nil
}

func (r *projectRepository) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	const query = `
		DELETE FROM projects
		WHERE id = $1
	`

	result, err := r.db.Exec(ctx, query, id)
	if err != nil {
		return fmt.Errorf("delete project: %w", err)
	}

	if result.RowsAffected() == 0 {
		return ErrProjectNotFound
	}

	return nil
}
