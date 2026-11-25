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
	// Same lock order as AIOps reviews: incident, proposal, deployment.
	var incidentLock bool
	err = tx.QueryRow(ctx, `SELECT public.cloudforge_lock_review_incident($1,$2,$3)`, incidentID, proposalID, digestHex).Scan(&incidentLock)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrRemediationApprovalRequired
	}
	if err != nil {
		return err
	}
	if !incidentLock {
		return ErrRemediationApprovalRequired
	}
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
		UPDATE aiops_remediation_proposals p
		SET dispatch_consumed_at = clock_timestamp()
		WHERE id = $1 AND incident_id = $2 AND target_deployment_id = $3
		  AND approved_environment = $4 AND dispatch_token_hash = $5
		  AND action = 'rerun_deployment' AND status = 'EXECUTING'
		  AND policy_decision = 'requires_approval' AND rejected_at IS NULL
		  AND approved_at IS NOT NULL AND approved_at <= clock_timestamp()
		  AND btrim(approved_by) <> '' AND approved_role = 'platform-engineer' AND approved_by <> proposed_by
		  AND expires_at > clock_timestamp() AND dispatch_consumed_at IS NULL
		  AND execution_idempotency_key IS NOT NULL AND btrim(execution_idempotency_key) <> ''
		  AND recommendation_version > 0 AND parameters = '{}'::jsonb AND resource_scope = $3
		  AND approved_contract = public.cloudforge_remediation_contract(p)
		  AND state_snapshot = public.cloudforge_remediation_current_state($2,$3)
		  AND project_id = (SELECT b.project_id FROM aiops_incident_projects b WHERE b.incident_id=$2)
		  AND EXISTS (SELECT 1 FROM deployments d WHERE d.id=$3::uuid AND d.project_id=p.project_id AND d.namespace='cf-'||d.project_id::text AND d.created_by<>'' AND d.created_by<>p.approved_by)
		  AND NOT EXISTS (SELECT 1 FROM aiops_remediation_proposals rejected WHERE rejected.incident_id=p.incident_id
		                  AND rejected.action_family=p.action_family AND rejected.status='REJECTED')
		  AND (p.alternative_of IS NULL OR EXISTS (
            SELECT 1 FROM aiops_remediation_proposals parent WHERE parent.id=p.alternative_of
            AND parent.incident_id=p.incident_id AND parent.project_id=p.project_id
            AND parent.alternative_result->>'proposal_id'=p.id
            AND parent.alternative_result->'generation_evidence'->>'provenance'='verified_resource_v1'
            AND parent.alternative_result->'generation_evidence'->>'project_id'=p.project_id::text
            AND parent.alternative_result->'generation_evidence'->>'signal'='deployment_health'
            AND parent.alternative_result->'generation_evidence'->>'state'='degraded'
            AND (parent.alternative_result->'generation_evidence'->>'observed_at')::numeric
                BETWEEN extract(epoch FROM clock_timestamp())-120 AND extract(epoch FROM clock_timestamp())
          ))
		  AND NOT EXISTS (SELECT 1 FROM aiops_advisory_rejections advisory WHERE advisory.incident_id=p.incident_id AND advisory.project_id=p.project_id AND advisory.effect=p.action_family)
		  AND EXISTS (SELECT 1 FROM auth_users u JOIN projects pr ON pr.id=p.project_id
		    WHERE u.username=p.approved_by AND u.active AND u.role='platform-engineer' AND pr.created_by IS NOT NULL
		    AND (pr.created_by=u.username OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=pr.id AND m.username=u.username AND m.level='maintainer')))
		  AND EXISTS (SELECT 1 FROM auth_users u JOIN projects pr ON pr.id=p.project_id
		    WHERE u.username=p.execution_requested_by AND u.active AND u.role='platform-engineer' AND pr.created_by IS NOT NULL
		    AND (pr.created_by=u.username OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=pr.id AND m.username=u.username AND m.level='maintainer')))
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
