package repository

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

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
	configuration, err := json.Marshal(resource.Configuration)
	if err != nil {
		return fmt.Errorf("marshal resource configuration: %w", err)
	}

	const query = `
		INSERT INTO infrastructure_resources (
			id,
			project_id,
			name,
			description,
			resource_type,
			provider,
			region,
			environment,
			configuration,
			status,
			terraform_directory,
			plan_path,
			plan_hash,
			plan_created_at,
			approval_expires_at,
			created_at,
			updated_at
		)
		VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8,
			$9, $10, $11, $12, $13, $14, $15, $16, $17
		)
	`

	_, err = r.pool.Exec(
		ctx,
		query,
		resource.ID,
		resource.ProjectID,
		resource.Name,
		resource.Description,
		resource.ResourceType,
		resource.Provider,
		resource.Region,
		resource.Environment,
		configuration,
		resource.Status,
		resource.TerraformDirectory,
		nullableString(resource.PlanPath),
		nullableString(resource.PlanHash),
		resource.PlanCreatedAt,
		resource.ApprovalExpiresAt,
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
		SELECT
			id,
			project_id,
			name,
			description,
			resource_type,
			provider,
			region,
			environment,
			configuration,
			status,
			terraform_directory,
			plan_path,
			plan_hash,
			plan_created_at,
			approval_expires_at,
			created_at,
			updated_at
		FROM infrastructure_resources
		WHERE id = $1
	`

	var resource model.InfrastructureResource
	var configuration []byte
	var resourceType *string
	var planPath *string
	var planHash *string
	var planCreatedAt *time.Time
	var approvalExpiresAt *time.Time

	err := r.pool.QueryRow(ctx, query, id).Scan(
		&resource.ID,
		&resource.ProjectID,
		&resource.Name,
		&resource.Description,
		&resourceType,
		&resource.Provider,
		&resource.Region,
		&resource.Environment,
		&configuration,
		&resource.Status,
		&resource.TerraformDirectory,
		&planPath,
		&planHash,
		&planCreatedAt,
		&approvalExpiresAt,
		&resource.CreatedAt,
		&resource.UpdatedAt,
	)

	if errors.Is(err, pgx.ErrNoRows) {
		return model.InfrastructureResource{}, ErrResourceNotFound
	}

	if err != nil {
		return model.InfrastructureResource{}, fmt.Errorf(
			"get infrastructure resource: %w",
			err,
		)
	}

	if resourceType != nil {
		resource.ResourceType = *resourceType
	}

	if planPath != nil {
		resource.PlanPath = *planPath
	}

	if planHash != nil {
		resource.PlanHash = *planHash
	}

	resource.PlanCreatedAt = planCreatedAt
	resource.ApprovalExpiresAt = approvalExpiresAt

	if err := decodeConfiguration(configuration, &resource); err != nil {
		return model.InfrastructureResource{}, err
	}

	return resource, nil
}

func (r *ResourceRepository) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.InfrastructureResource, error) {
	const query = `
		SELECT
			id,
			project_id,
			name,
			description,
			resource_type,
			provider,
			region,
			environment,
			configuration,
			status,
			terraform_directory,
			plan_path,
			plan_hash,
			plan_created_at,
			approval_expires_at,
			created_at,
			updated_at
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
		var configuration []byte
		var resourceType *string
		var planPath *string
		var planHash *string
		var planCreatedAt *time.Time
		var approvalExpiresAt *time.Time

		if err := rows.Scan(
			&resource.ID,
			&resource.ProjectID,
			&resource.Name,
			&resource.Description,
			&resourceType,
			&resource.Provider,
			&resource.Region,
			&resource.Environment,
			&configuration,
			&resource.Status,
			&resource.TerraformDirectory,
			&planPath,
			&planHash,
			&planCreatedAt,
			&approvalExpiresAt,
			&resource.CreatedAt,
			&resource.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf(
				"scan infrastructure resource: %w",
				err,
			)
		}

		if resourceType != nil {
			resource.ResourceType = *resourceType
		}

		if planPath != nil {
			resource.PlanPath = *planPath
		}

		if planHash != nil {
			resource.PlanHash = *planHash
		}

		resource.PlanCreatedAt = planCreatedAt
		resource.ApprovalExpiresAt = approvalExpiresAt

		if err := decodeConfiguration(configuration, &resource); err != nil {
			return nil, err
		}

		resources = append(resources, resource)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf(
			"iterate infrastructure resources: %w",
			err,
		)
	}

	return resources, nil
}

func (r *ResourceRepository) Update(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	configuration, err := json.Marshal(resource.Configuration)
	if err != nil {
		return fmt.Errorf("marshal resource configuration: %w", err)
	}

	const query = `
		UPDATE infrastructure_resources
		SET
			project_id = $1,
			name = $2,
			description = $3,
			resource_type = $4,
			provider = $5,
			region = $6,
			environment = $7,
			configuration = $8,
			status = $9,
			terraform_directory = $10,
			plan_path = $11,
			plan_hash = $12,
			plan_created_at = $13,
			approval_expires_at = $14,
			updated_at = $15
		WHERE id = $16
	`

	result, err := r.pool.Exec(
		ctx,
		query,
		resource.ProjectID,
		resource.Name,
		resource.Description,
		resource.ResourceType,
		resource.Provider,
		resource.Region,
		resource.Environment,
		configuration,
		resource.Status,
		resource.TerraformDirectory,
		nullableString(resource.PlanPath),
		nullableString(resource.PlanHash),
		resource.PlanCreatedAt,
		resource.ApprovalExpiresAt,
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

func nullableString(value string) *string {
	if value == "" {
		return nil
	}

	return &value
}

func decodeConfiguration(
	data []byte,
	resource *model.InfrastructureResource,
) error {
	resource.Configuration = make(map[string]any)

	if len(data) == 0 {
		return nil
	}

	if err := json.Unmarshal(data, &resource.Configuration); err != nil {
		return fmt.Errorf(
			"decode resource configuration: %w",
			err,
		)
	}

	return nil
}
