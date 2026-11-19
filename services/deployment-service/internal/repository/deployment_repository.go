package repository

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

var (
	ErrDeploymentConflict = errors.New("deployment changed during update")

	ErrDeploymentNotFound = errors.New(
		"deployment not found",
	)

	ErrDeploymentNotPending = errors.New(
		"deployment is not pending",
	)
)

type DeploymentRepository struct {
	pool          *pgxpool.Pool
	executionMode string
}

func NewDeploymentRepository(pool *pgxpool.Pool) *DeploymentRepository {
	return &DeploymentRepository{
		pool: pool, executionMode: "unknown",
	}
}

// SetExecutionMode configures the provenance written by the durable worker before it starts.
func (r *DeploymentRepository) SetExecutionMode(mode string) {
	r.executionMode = mode
}

func (r *DeploymentRepository) Create(
	ctx context.Context,
	deployment model.Deployment,
) error {
	if r.pool == nil {
		return errors.New("database pool is nil")
	}

	const query = `
		INSERT INTO deployments (
			id,
			project_id,
			environment,
			image,
			git_commit_sha,
			namespace,
			status,
			created_at,
			updated_at
		)
		VALUES (
			$1,
			$2,
			$3,
			$4,
			$5,
			$6,
			$7,
			$8,
			$9
		)
	`

	_, err := r.pool.Exec(
		ctx,
		query,
		deployment.ID,
		deployment.ProjectID,
		deployment.Environment,
		deployment.Image,
		deployment.GitCommitSHA,
		deployment.Namespace,
		deployment.Status,
		deployment.CreatedAt,
		deployment.UpdatedAt,
	)

	if err != nil {
		return fmt.Errorf("create deployment: %w", err)
	}

	return nil
}

func (r *DeploymentRepository) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.Deployment, error) {
	if r.pool == nil {
		return model.Deployment{}, errors.New("database pool is nil")
	}

	const query = `
		SELECT
			id,
			project_id,
			environment,
			image,
			git_commit_sha,
			namespace,
			status,
			execution_mode,
			created_at,
			updated_at
		FROM deployments
		WHERE id = $1
	`

	var deployment model.Deployment

	err := r.pool.QueryRow(
		ctx,
		query,
		id,
	).Scan(
		&deployment.ID,
		&deployment.ProjectID,
		&deployment.Environment,
		&deployment.Image,
		&deployment.GitCommitSHA,
		&deployment.Namespace,
		&deployment.Status,
		&deployment.ExecutionMode,
		&deployment.CreatedAt,
		&deployment.UpdatedAt,
	)

	if errors.Is(err, pgx.ErrNoRows) {
		return model.Deployment{}, ErrDeploymentNotFound
	}

	if err != nil {
		return model.Deployment{}, fmt.Errorf("get deployment by id: %w", err)
	}

	return deployment, nil
}

func (r *DeploymentRepository) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.Deployment, error) {
	if r.pool == nil {
		return nil, errors.New("database pool is nil")
	}

	query := `
		SELECT
			id,
			project_id,
			environment,
			image,
			git_commit_sha,
			namespace,
			status,
			execution_mode,
			created_at,
			updated_at
		FROM deployments r
	`
	args := []any{limit, offset}
	if member := identity.ListMember(ctx); member != "" {
		query += ` WHERE EXISTS (
			SELECT 1 FROM projects p WHERE p.id = r.project_id AND ` + identity.MembershipPredicate + `
		)`
		args = append(args, member)
	}
	query += ` ORDER BY created_at DESC LIMIT $1 OFFSET $2`

	rows, err := r.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("list deployments: %w", err)
	}

	defer rows.Close()

	deployments := make([]model.Deployment, 0)

	for rows.Next() {
		var deployment model.Deployment

		err := rows.Scan(
			&deployment.ID,
			&deployment.ProjectID,
			&deployment.Environment,
			&deployment.Image,
			&deployment.GitCommitSHA,
			&deployment.Namespace,
			&deployment.Status,
			&deployment.ExecutionMode,
			&deployment.CreatedAt,
			&deployment.UpdatedAt,
		)

		if err != nil {
			return nil, fmt.Errorf("scan deployment: %w", err)
		}

		deployments = append(deployments, deployment)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate deployments: %w", err)
	}

	return deployments, nil
}

func (r *DeploymentRepository) Update(
	ctx context.Context,
	deployment model.Deployment,
	expected model.Deployment,
) error {
	if r.pool == nil {
		return errors.New("database pool is nil")
	}

	const query = `
		UPDATE deployments
		SET
			environment = $2,
			image = $3,
			git_commit_sha = $4,
			namespace = $5,
			status = $6,
			updated_at = GREATEST($7::timestamptz, updated_at + interval '1 microsecond')
		WHERE id = $1 AND status = $8 AND updated_at = $9 AND execution_token IS NULL
		  AND (NOT $10::boolean OR (namespace = 'cf-' || project_id::text AND $5 = namespace))
	`

	result, err := r.pool.Exec(
		ctx,
		query,
		deployment.ID,
		deployment.Environment,
		deployment.Image,
		deployment.GitCommitSHA,
		deployment.Namespace,
		deployment.Status,
		deployment.UpdatedAt,
		expected.Status,
		expected.UpdatedAt,
		identity.FromContext(ctx).Human() && identity.FromContext(ctx).Role != "platform-engineer",
	)

	if err != nil {
		return fmt.Errorf("update deployment: %w", err)
	}

	if result.RowsAffected() == 0 {
		if _, err := r.GetByID(ctx, deployment.ID); err != nil {
			return err
		}
		return ErrDeploymentConflict
	}

	return nil
}

func (r *DeploymentRepository) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if r.pool == nil {
		return errors.New("database pool is nil")
	}

	const query = `
		DELETE FROM deployments
		WHERE id = $1 AND execution_token IS NULL
		  AND (status IN ('pending', 'queued') OR execution_mode = 'simulated')
	`

	result, err := r.pool.Exec(
		ctx,
		query,
		id,
	)

	if err != nil {
		return fmt.Errorf("delete deployment: %w", err)
	}

	if result.RowsAffected() == 0 {
		if _, err := r.GetByID(ctx, id); err != nil {
			return err
		}
		return fmt.Errorf("%w: execution history is retained or leased; deleting a record cannot remove a Kubernetes workload", ErrDeploymentConflict)
	}

	return nil
}
func (r *DeploymentRepository) ClaimPendingDeployment(
	ctx context.Context,
	id uuid.UUID,
	updatedAt time.Time,
) error {
	if r.pool == nil {
		return errors.New("database pool is nil")
	}

	const query = `
		UPDATE deployments
		SET
			status = 'queued',
			updated_at = GREATEST($2::timestamptz, updated_at + interval '1 microsecond')
		WHERE id = $1
		  AND status = 'pending'
		  AND (NOT $3::boolean OR namespace = 'cf-' || project_id::text)
	`

	result, err := r.pool.Exec(
		ctx,
		query,
		id,
		updatedAt,
		identity.FromContext(ctx).Human() && identity.FromContext(ctx).Role != "platform-engineer",
	)

	if err != nil {
		return fmt.Errorf(
			"claim pending deployment: %w",
			err,
		)
	}

	if result.RowsAffected() == 1 {
		return nil
	}

	var exists bool

	const existsQuery = `
		SELECT EXISTS (
			SELECT 1
			FROM deployments
			WHERE id = $1
		)
	`

	if err := r.pool.QueryRow(
		ctx,
		existsQuery,
		id,
	).Scan(&exists); err != nil {
		return fmt.Errorf(
			"check deployment existence: %w",
			err,
		)
	}

	if !exists {
		return ErrDeploymentNotFound
	}

	return ErrDeploymentNotPending
}

func (r *DeploymentRepository) ReleaseQueuedDeployment(
	ctx context.Context,
	id uuid.UUID,
	updatedAt time.Time,
) error {
	if r.pool == nil {
		return errors.New("database pool is nil")
	}

	const query = `
		UPDATE deployments
		SET
			status = 'pending',
			updated_at = GREATEST($2::timestamptz, updated_at + interval '1 microsecond')
		WHERE id = $1
		  AND status = 'queued'
	`

	result, err := r.pool.Exec(
		ctx,
		query,
		id,
		updatedAt,
	)

	if err != nil {
		return fmt.Errorf(
			"release queued deployment: %w",
			err,
		)
	}

	if result.RowsAffected() == 1 {
		return nil
	}

	return ErrDeploymentNotFound
}

func (r *DeploymentRepository) GetPreviousSuccessfulDeployment(
	ctx context.Context,
	projectID uuid.UUID,
	environment string,
	excludeDeploymentID uuid.UUID,
) (model.Deployment, error) {
	if r.pool == nil {
		return model.Deployment{}, errors.New("database pool is nil")
	}

	const query = `
		SELECT previous.id, previous.project_id, previous.environment, previous.image,
		       previous.git_commit_sha, previous.namespace, previous.status,
		       previous.execution_mode, previous.created_at, previous.updated_at
		FROM deployments current
		JOIN deployments previous ON previous.project_id = current.project_id
		  AND previous.environment = current.environment AND previous.namespace = current.namespace
		  AND previous.created_at < current.created_at
		WHERE current.id = $3 AND current.project_id = $1 AND current.environment = $2
		  AND current.execution_mode = $4 AND current.status IN ('succeeded', 'failed')
		  AND previous.execution_mode = $4 AND previous.status = 'succeeded'
		  AND ($4 <> 'kubernetes' OR previous.image ~ '@sha256:[a-fA-F0-9]{64}$')
		ORDER BY previous.created_at DESC, previous.id DESC
		LIMIT 1
	`

	var deployment model.Deployment

	err := r.pool.QueryRow(
		ctx,
		query,
		projectID,
		environment,
		excludeDeploymentID,
		r.executionMode,
	).Scan(
		&deployment.ID,
		&deployment.ProjectID,
		&deployment.Environment,
		&deployment.Image,
		&deployment.GitCommitSHA,
		&deployment.Namespace,
		&deployment.Status,
		&deployment.ExecutionMode,
		&deployment.CreatedAt,
		&deployment.UpdatedAt,
	)

	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return model.Deployment{}, ErrDeploymentNotFound
		}

		return model.Deployment{}, fmt.Errorf(
			"get previous successful deployment: %w",
			err,
		)
	}

	return deployment, nil
}
