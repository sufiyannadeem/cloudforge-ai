package repository

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

var ErrLeaseLost = errors.New("execution lease lost or fenced out")

const (
	acquireLeaseQuery = `
INSERT INTO infrastructure_execution_leases (
    resource_id, owner_id, operation, fencing_token, lease_expires_at, acquired_at, heartbeat_at
) VALUES (
    $1, $2, $3, 1, clock_timestamp() + ($4 * interval '1 millisecond'), clock_timestamp(), clock_timestamp()
)
ON CONFLICT (resource_id) DO UPDATE
SET owner_id = EXCLUDED.owner_id,
    operation = EXCLUDED.operation,
    fencing_token = infrastructure_execution_leases.fencing_token + 1,
    lease_expires_at = clock_timestamp() + ($4 * interval '1 millisecond'),
    acquired_at = clock_timestamp(),
    heartbeat_at = clock_timestamp()
WHERE infrastructure_execution_leases.lease_expires_at <= clock_timestamp()
RETURNING resource_id, owner_id, operation, fencing_token, lease_expires_at, acquired_at, heartbeat_at;
`

	heartbeatLeaseQuery = `
UPDATE infrastructure_execution_leases
SET heartbeat_at = clock_timestamp(),
    lease_expires_at = clock_timestamp() + ($4 * interval '1 millisecond')
WHERE resource_id = $1 AND owner_id = $2 AND fencing_token = $3
  AND lease_expires_at > clock_timestamp();
`

	releaseLeaseQuery = `
UPDATE infrastructure_execution_leases
SET lease_expires_at = clock_timestamp()
WHERE resource_id = $1 AND owner_id = $2 AND fencing_token = $3
  AND lease_expires_at > clock_timestamp();
`

	getLeaseQuery = `
SELECT resource_id, owner_id, operation, fencing_token, lease_expires_at, acquired_at, heartbeat_at
FROM infrastructure_execution_leases
WHERE resource_id = $1;
`
)

func (r *ResourceRepository) AcquireExecutionLease(
	ctx context.Context,
	resourceID uuid.UUID,
	ownerID string,
	operation string,
	ttl time.Duration,
) (model.ExecutionLease, error) {
	if ownerID == "" || operation == "" || ttl <= 0 {
		return model.ExecutionLease{}, ErrResourceConflict
	}

	var lease model.ExecutionLease
	err := r.pool.QueryRow(
		ctx,
		acquireLeaseQuery,
		resourceID,
		ownerID,
		operation,
		ttl.Milliseconds(),
	).Scan(
		&lease.ResourceID,
		&lease.OwnerID,
		&lease.Operation,
		&lease.FencingToken,
		&lease.LeaseExpiresAt,
		&lease.AcquiredAt,
		&lease.HeartbeatAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return model.ExecutionLease{}, ErrResourceConflict
		}
		return model.ExecutionLease{}, err
	}

	return lease, nil
}

func (r *ResourceRepository) HeartbeatExecutionLease(
	ctx context.Context,
	resourceID uuid.UUID,
	ownerID string,
	fencingToken int64,
	ttl time.Duration,
) error {
	tag, err := r.pool.Exec(
		ctx,
		heartbeatLeaseQuery,
		resourceID,
		ownerID,
		fencingToken,
		ttl.Milliseconds(),
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrLeaseLost
	}
	return nil
}

func (r *ResourceRepository) ReleaseExecutionLease(
	ctx context.Context,
	resourceID uuid.UUID,
	ownerID string,
	fencingToken int64,
) error {
	tag, err := r.pool.Exec(
		ctx,
		releaseLeaseQuery,
		resourceID,
		ownerID,
		fencingToken,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrLeaseLost
	}
	return nil
}

func (r *ResourceRepository) GetExecutionLease(
	ctx context.Context,
	resourceID uuid.UUID,
) (model.ExecutionLease, error) {
	var lease model.ExecutionLease
	err := r.pool.QueryRow(
		ctx,
		getLeaseQuery,
		resourceID,
	).Scan(
		&lease.ResourceID,
		&lease.OwnerID,
		&lease.Operation,
		&lease.FencingToken,
		&lease.LeaseExpiresAt,
		&lease.AcquiredAt,
		&lease.HeartbeatAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return model.ExecutionLease{}, ErrResourceNotFound
		}
		return model.ExecutionLease{}, err
	}
	return lease, nil
}
