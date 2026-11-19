package repository

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

var ErrExecutionLeaseLost = errors.New("deployment execution lease lost")

type ExecutionLease struct {
	DeploymentID           uuid.UUID
	Token                  uuid.UUID // Also identifies the attempt owned by the lease.
	Reconcile              bool
	ModeMismatch           bool
	ProgressiveUnsupported bool
	Environment            string
}

func (r *DeploymentRepository) ClaimExecution(ctx context.Context, ttl time.Duration) (ExecutionLease, error) {
	tx, err := r.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return ExecutionLease{}, err
	}
	defer tx.Rollback(ctx)

	lease := ExecutionLease{Token: uuid.New()}
	var startedAt time.Time
	var previousMode string
	var workloadScope string
	var progressive bool
	err = tx.QueryRow(ctx, `
		SELECT id, environment, status = 'running' AND (execution_started OR execution_token IS NULL), execution_mode, clock_timestamp(), project_id::text || '/' || namespace, strategy->>'type' IN ('blue-green','canary')
  FROM deployments d
  WHERE (status = 'queued'
     OR (status = 'running' AND (execution_expires_at IS NULL OR execution_expires_at <= clock_timestamp())))
  AND NOT EXISTS (SELECT 1 FROM deployments active WHERE active.project_id=d.project_id
    AND active.namespace=d.namespace AND active.id<>d.id AND active.status='running')
		ORDER BY updated_at, id
		LIMIT 1 FOR UPDATE SKIP LOCKED
	`).Scan(&lease.DeploymentID, &lease.Environment, &lease.Reconcile, &previousMode, &startedAt, &workloadScope, &progressive)
	if errors.Is(err, pgx.ErrNoRows) {
		return ExecutionLease{}, nil
	}
	if err != nil {
		return ExecutionLease{}, err
	}

	// Different deployment rows may target the same controller/Service selector.
	// Serialize the scope check and claim, not just each individual deployment ID.
	var locked bool
	if err := tx.QueryRow(ctx, "SELECT pg_try_advisory_xact_lock(hashtextextended($1,0))", workloadScope).Scan(&locked); err != nil {
		return ExecutionLease{}, err
	}
	if !locked {
		return ExecutionLease{}, nil
	}
	var occupied bool
	if err := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM deployments WHERE project_id::text || '/' || namespace=$1 AND id<>$2 AND status='running')`, workloadScope, lease.DeploymentID).Scan(&occupied); err != nil {
		return ExecutionLease{}, err
	}
	if occupied {
		return ExecutionLease{}, nil
	}
	mode := r.executionMode
	lease.ProgressiveUnsupported = progressive && mode != "kubernetes"
	if lease.Reconcile && previousMode != "unknown" && previousMode != mode {
		lease.ModeMismatch = true
		mode = previousMode
	}

	// Legacy running deployments may also have an unfinished attempt.
	_, err = tx.Exec(ctx, `
		UPDATE deployment_attempts
		SET status = 'failed', error_message = 'Worker ownership expired before completion',
		    completed_at = GREATEST(started_at, $2::timestamptz),
		    duration_ms = GREATEST(0, EXTRACT(EPOCH FROM ($2::timestamptz - started_at)) * 1000)::bigint
		WHERE deployment_id = $1 AND status = 'running'
	`, lease.DeploymentID, startedAt)
	if err != nil {
		return ExecutionLease{}, err
	}

	err = insertDeploymentAttempt(ctx, tx, model.DeploymentAttempt{
		ID: lease.Token, DeploymentID: lease.DeploymentID, Status: model.AttemptStatusRunning,
		StartedAt: startedAt, CreatedAt: startedAt, ExecutionMode: mode,
	})
	if err != nil {
		return ExecutionLease{}, err
	}

	_, err = tx.Exec(ctx, `
		UPDATE deployments
		SET status = 'running', execution_mode = $5, execution_token = $2, execution_started = $3,
		    execution_expires_at = clock_timestamp() + $4::double precision * interval '1 millisecond',
		    updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
		WHERE id = $1
	`, lease.DeploymentID, lease.Token, lease.Reconcile, float64(ttl.Milliseconds()), mode)
	if err != nil {
		return ExecutionLease{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ExecutionLease{}, err
	}
	return lease, nil
}

func (r *DeploymentRepository) RenewExecution(ctx context.Context, lease ExecutionLease, ttl time.Duration) error {
	tag, err := r.pool.Exec(ctx, `
		UPDATE deployments SET execution_expires_at = clock_timestamp() + $3::double precision * interval '1 millisecond'
		WHERE id = $1 AND execution_token = $2 AND status = 'running' AND execution_expires_at > clock_timestamp()
	`, lease.DeploymentID, lease.Token, float64(ttl.Milliseconds()))
	if err == nil && tag.RowsAffected() != 1 {
		return ErrExecutionLeaseLost
	}
	return err
}

// BeginExecution records the uncertainty boundary before any external mutation.
func (r *DeploymentRepository) BeginExecution(ctx context.Context, lease ExecutionLease) error {
	tag, err := r.pool.Exec(ctx, `
		UPDATE deployments SET execution_started = TRUE
		WHERE id = $1 AND execution_token = $2 AND status = 'running'
		  AND execution_expires_at > clock_timestamp() AND NOT execution_started
	`, lease.DeploymentID, lease.Token)
	if err == nil && tag.RowsAffected() != 1 {
		return ErrExecutionLeaseLost
	}
	return err
}

func (r *DeploymentRepository) FinishExecution(ctx context.Context, lease ExecutionLease, executionErr error) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	status := model.DeploymentStatusSucceeded
	var message *string
	if executionErr != nil {
		status = model.DeploymentStatusFailed
		detail := executionErr.Error()
		message = &detail
	}

	tag, err := tx.Exec(ctx, `
		UPDATE deployments
		SET status = $3, execution_token = NULL, execution_expires_at = NULL,
		    updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
		WHERE id = $1 AND execution_token = $2 AND status = 'running' AND execution_expires_at > clock_timestamp()
	`, lease.DeploymentID, lease.Token, status)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrExecutionLeaseLost
	}

	tag, err = tx.Exec(ctx, `
		UPDATE deployment_attempts
		SET status = $3, error_message = $4,
		    completed_at = GREATEST(started_at, clock_timestamp()),
		    duration_ms = GREATEST(0, EXTRACT(EPOCH FROM (clock_timestamp() - started_at)) * 1000)::bigint
		WHERE id = $2 AND deployment_id = $1 AND status = 'running'
	`, lease.DeploymentID, lease.Token, status, message)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return errors.New("execution attempt is missing or already completed")
	}
	return tx.Commit(ctx)
}
