package repository

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

var ErrResourceNotFound = errors.New("infrastructure resource not found")

type ResourceRepository struct {
	pool *pgxpool.Pool
}

func NewResourceRepository(pool *pgxpool.Pool) *ResourceRepository {
	return &ResourceRepository{pool: pool}
}

func (r *ResourceRepository) Create(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	const query = `
		INSERT INTO infrastructure_resources (
			id, name, description, provider, region,
			environment, status, terraform_directory,
			created_at, updated_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
	`

	_, err := r.pool.Exec(
		ctx,
		query,
		resource.ID,
		resource.Name,
		resource.Description,
		resource.Provider,
		resource.Region,
		resource.Environment,
		resource.Status,
		resource.TerraformDirectory,
		resource.CreatedAt,
		resource.UpdatedAt,
	)

	if err != nil {
		return fmt.Errorf("create infrastructure resource: %w", err)
	}

	return nil
}

func (r *ResourceRepository) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	const query = `
		SELECT id, name, description, provider, region,
		       environment, status, terraform_directory,
		       created_at, updated_at
		FROM infrastructure_resources
		WHERE id = $1
	`

	var resource model.InfrastructureResource

	err := r.pool.QueryRow(ctx, query, id).Scan(
		&resource.ID,
		&resource.Name,
		&resource.Description,
		&resource.Provider,
		&resource.Region,
		&resource.Environment,
		&resource.Status,
		&resource.TerraformDirectory,
		&resource.CreatedAt,
		&resource.UpdatedAt,
	)

	if errors.Is(err, pgx.ErrNoRows) {
		return model.InfrastructureResource{}, ErrResourceNotFound
	}

	if err != nil {
		return model.InfrastructureResource{}, fmt.Errorf(
			"get infrastructure resource: %w", err,
		)
	}

	return resource, nil
}

func (r *ResourceRepository) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.InfrastructureResource, error) {
	const query = `
		SELECT id, name, description, provider, region,
		       environment, status, terraform_directory,
		       created_at, updated_at
		FROM infrastructure_resources
		ORDER BY created_at DESC
		LIMIT $1 OFFSET $2
	`

	rows, err := r.pool.Query(ctx, query, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("list infrastructure resources: %w", err)
	}
	defer rows.Close()

	resources := make([]model.InfrastructureResource, 0)

	for rows.Next() {
		var resource model.InfrastructureResource

		if err := rows.Scan(
			&resource.ID,
			&resource.Name,
			&resource.Description,
			&resource.Provider,
			&resource.Region,
			&resource.Environment,
			&resource.Status,
			&resource.TerraformDirectory,
			&resource.CreatedAt,
			&resource.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan infrastructure resource: %w", err)
		}

		resources = append(resources, resource)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate infrastructure resources: %w", err)
	}

	return resources, nil
}

func (r *ResourceRepository) Update(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	const query = `
		UPDATE infrastructure_resources
		SET name = $1,
		    description = $2,
		    provider = $3,
		    region = $4,
		    environment = $5,
		    status = $6,
		    terraform_directory = $7,
		    updated_at = $8
		WHERE id = $9
	`

	result, err := r.pool.Exec(
		ctx,
		query,
		resource.Name,
		resource.Description,
		resource.Provider,
		resource.Region,
		resource.Environment,
		resource.Status,
		resource.TerraformDirectory,
		resource.UpdatedAt,
		resource.ID,
	)

	if err != nil {
		return fmt.Errorf("update infrastructure resource: %w", err)
	}

	if result.RowsAffected() == 0 {
		return ErrResourceNotFound
	}

	return nil
}

func (r *ResourceRepository) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	const query = `
		DELETE FROM infrastructure_resources
		WHERE id = $1
	`

	result, err := r.pool.Exec(ctx, query, id)
	if err != nil {
		return fmt.Errorf("delete infrastructure resource: %w", err)
	}

	if result.RowsAffected() == 0 {
		return ErrResourceNotFound
	}

	return nil
}
