package repository

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

var (
	ErrResourceNotFound = errors.New("infrastructure resource not found")
	ErrResourceConflict = errors.New("infrastructure resource state changed concurrently")
)

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
			destroy_plan_path,
			destroy_plan_hash,
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
	var destroyPlanPath *string
	var destroyPlanHash *string

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
		&destroyPlanPath,
		&destroyPlanHash,
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

	if destroyPlanPath != nil {
		resource.DestroyPlanPath = *destroyPlanPath
	}

	if destroyPlanHash != nil {
		resource.DestroyPlanHash = *destroyPlanHash
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
			destroy_plan_path,
			destroy_plan_hash,
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
		var destroyPlanPath *string
		var destroyPlanHash *string

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
			&destroyPlanPath,
			&destroyPlanHash,
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

		if destroyPlanPath != nil {
			resource.DestroyPlanPath = *destroyPlanPath
		}

		if destroyPlanHash != nil {
			resource.DestroyPlanHash = *destroyPlanHash
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

// TransitionStatus performs a compare-and-set transition so concurrent requests
// cannot both claim the same provisioning state.
func (r *ResourceRepository) TransitionStatus(
	ctx context.Context,
	id uuid.UUID,
	from []model.ResourceStatus,
	to model.ResourceStatus,
) error {
	if len(from) == 0 {
		return ErrResourceConflict
	}

	args := []any{to, time.Now().UTC(), id}
	placeholders := make([]string, 0, len(from))
	for _, status := range from {
		args = append(args, status)
		placeholders = append(placeholders, fmt.Sprintf("$%d", len(args)))
	}

	query := fmt.Sprintf(`
		UPDATE infrastructure_resources
		SET status = $1, updated_at = $2
		WHERE id = $3 AND status IN (%s)
	`, strings.Join(placeholders, ", "))

	result, err := r.pool.Exec(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("transition infrastructure resource status: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrResourceConflict
	}
	return nil
}

// SavePlan writes plan metadata and opens the approval window atomically.
func (r *ResourceRepository) SavePlan(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	const query = `
		UPDATE infrastructure_resources
		SET terraform_directory = $1,
		    plan_path = $2,
		    plan_hash = $3,
		    plan_created_at = $4,
		    approval_expires_at = $5,
		    status = $6,
		    updated_at = $7
		WHERE id = $8 AND status = $9
	`
	result, err := r.pool.Exec(
		ctx, query,
		resource.TerraformDirectory,
		nullableString(resource.PlanPath),
		nullableString(resource.PlanHash),
		resource.PlanCreatedAt,
		resource.ApprovalExpiresAt,
		model.ResourceStatusAwaitingApproval,
		time.Now().UTC(),
		resource.ID,
		model.ResourceStatusPlanning,
	)
	if err != nil {
		return fmt.Errorf("persist terraform plan: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrResourceConflict
	}
	return nil
}

// SaveDestroyPlan persists the destroy plan artifact and opens the destroy
// approval window. It only succeeds while the resource is claimed in planning.
func (r *ResourceRepository) SaveDestroyPlan(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	const query = `
		UPDATE infrastructure_resources
		SET destroy_plan_path = $1,
		    destroy_plan_hash = $2,
		    approval_expires_at = $3,
		    status = $4,
		    updated_at = $5
		WHERE id = $6 AND status = $7
	`
	result, err := r.pool.Exec(
		ctx, query,
		nullableString(resource.DestroyPlanPath),
		nullableString(resource.DestroyPlanHash),
		resource.ApprovalExpiresAt,
		model.ResourceStatusAwaitingDestroyApproval,
		time.Now().UTC(),
		resource.ID,
		model.ResourceStatusPlanning,
	)
	if err != nil {
		return fmt.Errorf("persist terraform destroy plan: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrResourceConflict
	}
	return nil
}

// UpdateEditable updates only fields present in the request. The expected
// status predicate prevents a stale edit from racing with a Plan/Apply claim.
func (r *ResourceRepository) UpdateEditable(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateResourceInput,
	expectedStatus model.ResourceStatus,
) error {
	sets := make([]string, 0, 6)
	args := make([]any, 0, 8)
	add := func(column string, value any) {
		args = append(args, value)
		sets = append(sets, fmt.Sprintf("%s = $%d", column, len(args)))
	}
	if input.Name != nil {
		add("name", *input.Name)
	}
	if input.Description != nil {
		add("description", *input.Description)
	}
	if input.Region != nil {
		add("region", *input.Region)
	}
	if input.Environment != nil {
		add("environment", *input.Environment)
	}
	if input.TerraformDirectory != nil {
		add("terraform_directory", *input.TerraformDirectory)
	}
	if input.Configuration != nil {
		configuration, err := json.Marshal(input.Configuration)
		if err != nil {
			return fmt.Errorf("marshal resource configuration: %w", err)
		}
		add("configuration", configuration)
	}
	add("updated_at", time.Now().UTC())
	args = append(args, id, expectedStatus)
	query := fmt.Sprintf(`UPDATE infrastructure_resources SET %s WHERE id = $%d AND status = $%d`,
		strings.Join(sets, ", "), len(args)-1, len(args))
	result, err := r.pool.Exec(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("update editable infrastructure resource fields: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrResourceConflict
	}
	return nil
}

func (r *ResourceRepository) DeleteIfStatusAllowed(
	ctx context.Context,
	id uuid.UUID,
) error {
	const query = `
		DELETE FROM infrastructure_resources
		WHERE id = $1
		  AND status NOT IN (
			'planning',
			'awaiting_approval',
			'provisioning',
			'active',
			'destroying',
			'awaiting_destroy_approval'
		  )
	`

	result, err := r.pool.Exec(ctx, query, id)
	if err != nil {
		return fmt.Errorf("delete infrastructure resource: %w", err)
	}

	if result.RowsAffected() == 0 {
		// Distinguish a missing resource from a resource whose status
		// prevents deletion.
		_, err := r.GetByID(ctx, id)
		if err != nil {
			return err
		}
		return ErrResourceConflict
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
