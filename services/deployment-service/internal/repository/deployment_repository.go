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
)

var (
	ErrDeploymentNotFound = errors.New(
		"deployment not found",
	)

	ErrDeploymentNotPending = errors.New(
		"deployment is not pending",
	)
)

type DeploymentRepository struct {
	pool *pgxpool.Pool
}

func NewDeploymentRepository(pool *pgxpool.Pool) *DeploymentRepository {
	return &DeploymentRepository{
		pool: pool,
	}
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

	const query = `
		SELECT
			id,
			project_id,
			environment,
			image,
			git_commit_sha,
			namespace,
			status,
			created_at,
			updated_at
		FROM deployments
		ORDER BY created_at DESC
		LIMIT $1 OFFSET $2
	`

	rows, err := r.pool.Query(
		ctx,
		query,
		limit,
		offset,
	)

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
			updated_at = $7
		WHERE id = $1
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
	)

	if err != nil {
		return fmt.Errorf("update deployment: %w", err)
	}

	if result.RowsAffected() == 0 {
		return ErrDeploymentNotFound
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
		WHERE id = $1
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
		return ErrDeploymentNotFound
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
			updated_at = $2
		WHERE id = $1
		  AND status = 'pending'
	`

	result, err := r.pool.Exec(
		ctx,
		query,
		id,
		updatedAt,
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
			updated_at = $2
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
