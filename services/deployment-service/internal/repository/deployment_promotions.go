package repository

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

var ErrPromotionDenied = errors.New("independent active Platform Engineer approval of this running blue-green revision is required; approval may already be consumed")

type PromotionAudit struct {
	ID              uuid.UUID       `json:"id"`
	Actor           string          `json:"actor"`
	UID             string          `json:"resource_uid"`
	ResourceVersion string          `json:"resource_version"`
	Binding         json.RawMessage `json:"binding"`
	Outcome         string          `json:"outcome"`
	ApprovedAt      time.Time       `json:"approved_at"`
}

func (r *DeploymentRepository) ClaimPromotion(ctx context.Context, id uuid.UUID, uid, version string) (uuid.UUID, error) {
	caller := identity.FromContext(ctx)
	if !caller.Human() || caller.Role != "platform-engineer" || caller.Expiry <= time.Now().Unix() {
		return uuid.Nil, ErrPromotionDenied
	}
	auditID := uuid.New()
	err := r.pool.QueryRow(ctx, `
 INSERT INTO deployment_promotions (id,deployment_id,actor,request_nonce,resource_uid,resource_version,binding)
 SELECT $2,d.id,$3,$4,$5,$6,jsonb_build_object('project_id',d.project_id,'environment',d.environment,
 'namespace',d.namespace,'image',d.image,'git_commit_sha',d.git_commit_sha,'strategy',d.strategy,'requester',d.created_by)
 FROM deployments d JOIN auth_users u ON u.username=$3 AND u.active AND u.role='platform-engineer'
 WHERE d.id=$1 AND d.status='running' AND d.strategy->>'type'='blue-green'
 AND d.execution_mode='kubernetes' AND d.execution_token IS NOT NULL AND d.execution_expires_at>clock_timestamp()
 AND d.created_by<>'' AND d.created_by<>$3 AND d.namespace='cf-'||d.project_id::text
 ON CONFLICT DO NOTHING RETURNING id
 `, id, auditID, caller.Subject, caller.Nonce, uid, version).Scan(&auditID)
	if errors.Is(err, pgx.ErrNoRows) {
		err = ErrPromotionDenied
	}
	return auditID, err
}
func (r *DeploymentRepository) CompletePromotion(ctx context.Context, id uuid.UUID, submitted bool) error {
	outcome := "uncertain"
	if submitted {
		outcome = "submitted"
	}
	_, err := r.pool.Exec(ctx, `UPDATE deployment_promotions SET outcome=$2,completed_at=clock_timestamp() WHERE id=$1 AND outcome='claimed'`, id, outcome)
	return err
}
func (r *DeploymentRepository) PromotionHistory(ctx context.Context, id uuid.UUID) ([]PromotionAudit, error) {
	rows, err := r.pool.Query(ctx, `SELECT id,actor,resource_uid,resource_version,binding,outcome,approved_at FROM deployment_promotions WHERE deployment_id=$1 ORDER BY approved_at DESC LIMIT 10`, id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	history := []PromotionAudit{}
	for rows.Next() {
		var item PromotionAudit
		if err := rows.Scan(&item.ID, &item.Actor, &item.UID, &item.ResourceVersion, &item.Binding, &item.Outcome, &item.ApprovedAt); err != nil {
			return nil, err
		}
		history = append(history, item)
	}
	return history, rows.Err()
}

// Progressive history prevents disabling the feature flag from hiding an
// existing controller when a later native revision targets the same workload.
func (r *DeploymentRepository) HasProgressiveHistory(ctx context.Context, id uuid.UUID) (bool, error) {
	var exists bool
	err := r.pool.QueryRow(ctx, `SELECT EXISTS(
 SELECT 1 FROM deployments current JOIN deployments previous
 ON previous.project_id=current.project_id AND previous.namespace=current.namespace
 WHERE current.id=$1 AND previous.id<>current.id AND previous.execution_mode='kubernetes'
 AND previous.strategy->>'type' IN ('blue-green','canary'))`, id).Scan(&exists)
	return exists, err
}
