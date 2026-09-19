package repository

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type DeploymentAttemptRepository struct {
	db *pgxpool.Pool
}

func NewDeploymentAttemptRepository(
	db *pgxpool.Pool,
) (*DeploymentAttemptRepository, error) {
	if db == nil {
		return nil, errors.New("database pool is required")
	}

	return &DeploymentAttemptRepository{
		db: db,
	}, nil
}

func (r *DeploymentAttemptRepository) Create(
	ctx context.Context,
	attempt model.DeploymentAttempt,
) error {
	const query = `
		INSERT INTO deployment_attempts (
			id,
			deployment_id,
			attempt_number,
			status,
			error_message,
			started_at,
			completed_at,
			duration_ms,
			created_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
	`

	_, err := r.db.Exec(
		ctx,
		query,
		attempt.ID,
		attempt.DeploymentID,
		attempt.AttemptNumber,
		attempt.Status,
		attempt.ErrorMessage,
		attempt.StartedAt,
		attempt.CompletedAt,
		attempt.DurationMs,
		attempt.CreatedAt,
	)

	if err != nil {
		return fmt.Errorf("create deployment attempt: %w", err)
	}

	return nil
}

func (r *DeploymentAttemptRepository) Update(
	ctx context.Context,
	attempt model.DeploymentAttempt,
) error {
	const query = `
		UPDATE deployment_attempts
		SET
			status = $2,
			error_message = $3,
			completed_at = $4,
			duration_ms = $5
		WHERE id = $1
	`

	result, err := r.db.Exec(
		ctx,
		query,
		attempt.ID,
		attempt.Status,
		attempt.ErrorMessage,
		attempt.CompletedAt,
		attempt.DurationMs,
	)

	if err != nil {
		return fmt.Errorf("update deployment attempt: %w", err)
	}

	if result.RowsAffected() == 0 {
		return errors.New("deployment attempt not found")
	}

	return nil
}

func (r *DeploymentAttemptRepository) GetNextAttemptNumber(
	ctx context.Context,
	deploymentID uuid.UUID,
) (int, error) {
	const query = `
		SELECT COALESCE(MAX(attempt_number), 0) + 1
		FROM deployment_attempts
		WHERE deployment_id = $1
	`

	var nextNumber int

	err := r.db.QueryRow(
		ctx,
		query,
		deploymentID,
	).Scan(&nextNumber)

	if err != nil {
		return 0, fmt.Errorf("get next attempt number: %w", err)
	}

	return nextNumber, nil
}

func (r *DeploymentAttemptRepository) ListByDeploymentID(
	ctx context.Context,
	deploymentID uuid.UUID,
	limit int,
	offset int,
) ([]model.DeploymentAttempt, error) {
	if limit <= 0 {
		limit = 20
	}

	if limit > 100 {
		limit = 100
	}

	if offset < 0 {
		offset = 0
	}

	const query = `
		SELECT
			id,
			deployment_id,
			attempt_number,
			status,
			error_message,
			started_at,
			completed_at,
			duration_ms,
			created_at
		FROM deployment_attempts
		WHERE deployment_id = $1
		ORDER BY attempt_number DESC
		LIMIT $2 OFFSET $3
	`

	rows, err := r.db.Query(
		ctx,
		query,
		deploymentID,
		limit,
		offset,
	)

	if err != nil {
		return nil, fmt.Errorf("list deployment attempts: %w", err)
	}

	defer rows.Close()

	attempts := make([]model.DeploymentAttempt, 0)

	for rows.Next() {
		var attempt model.DeploymentAttempt

		err := rows.Scan(
			&attempt.ID,
			&attempt.DeploymentID,
			&attempt.AttemptNumber,
			&attempt.Status,
			&attempt.ErrorMessage,
			&attempt.StartedAt,
			&attempt.CompletedAt,
			&attempt.DurationMs,
			&attempt.CreatedAt,
		)

		if err != nil {
			return nil, fmt.Errorf(
				"scan deployment attempt: %w",
				err,
			)
		}

		attempts = append(attempts, attempt)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf(
			"iterate deployment attempts: %w",
			err,
		)
	}

	return attempts, nil
}

var _ DeploymentAttemptStore = (*DeploymentAttemptRepository)(nil)
