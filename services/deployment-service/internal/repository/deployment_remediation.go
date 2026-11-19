package repository

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

var ErrRemediationApprovalRequired = errors.New("valid unused remediation approval required")

// ClaimRemediation consumes the verified AIOps dispatch in the same transaction
// that queues the exact deployment. Both services use the same PostgreSQL database.
func (r *DeploymentRepository) ClaimRemediation(ctx context.Context, target uuid.UUID, proposalID, incidentID, dispatchToken string) error {
	tx, err := r.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	digest := sha256.Sum256([]byte(dispatchToken))
	digestHex := hex.EncodeToString(digest[:])
	var lockedID string
	err = tx.QueryRow(ctx, `
		SELECT id FROM aiops_remediation_proposals
		WHERE id = $1 AND dispatch_token_hash = $2 AND dispatch_consumed_at IS NULL
		FOR UPDATE
	`, proposalID, digestHex).Scan(&lockedID)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrRemediationApprovalRequired
	}
	if err != nil {
		return err
	}

	var environment string
	err = tx.QueryRow(ctx, `
		SELECT environment FROM deployments WHERE id = $1 AND status = 'pending' FOR UPDATE
	`, target).Scan(&environment)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrRemediationApprovalRequired
	}
	if err != nil {
		return err
	}

	tag, err := tx.Exec(ctx, `
		UPDATE aiops_remediation_proposals
		SET dispatch_consumed_at = clock_timestamp()
		WHERE id = $1 AND incident_id = $2 AND target_deployment_id = $3
		  AND approved_environment = $4 AND dispatch_token_hash = $5
		  AND action = 'rerun_deployment' AND status = 'EXECUTING'
		  AND policy_decision = 'requires_approval' AND rejected_at IS NULL
		  AND approved_at IS NOT NULL AND approved_at <= clock_timestamp()
		  AND btrim(approved_by) <> '' AND approved_role IN ('sre', 'platform-engineer')
		  AND expires_at > clock_timestamp() AND dispatch_consumed_at IS NULL
		  AND execution_idempotency_key IS NOT NULL
	`, proposalID, incidentID, target.String(), environment, digestHex)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrRemediationApprovalRequired
	}

	tag, err = tx.Exec(ctx, `
		UPDATE deployments SET status = 'queued',
		    updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
		WHERE id = $1 AND status = 'pending'
	`, target)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrRemediationApprovalRequired
	}
	return tx.Commit(ctx)
}
