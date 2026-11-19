package repository

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

var ErrReviewForbidden = errors.New("requesters cannot decide their own plan")

type pendingReviewKey struct{}

func WithPendingReviews(ctx context.Context) context.Context {
	return context.WithValue(ctx, pendingReviewKey{}, true)
}

const planReviewsSelect = `
	SELECT operation, revision, plan_hash, project_id, environment, requester,
	       submitted_by, submitted_at, expires_at, status, decided_by, decided_at,
	       executed_by, execution_started_at, finished_at
	FROM infrastructure_plan_reviews WHERE resource_id = $1
`

func (r *ResourceRepository) PlanReviews(ctx context.Context, id uuid.UUID) ([]model.PlanReview, error) {
	rows, err := r.pool.Query(ctx, planReviewsSelect+` ORDER BY submitted_at DESC LIMIT 30`, id)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, pgx.RowToStructByPos[model.PlanReview])
}

const failedExecutionExists = `EXISTS (
    SELECT 1 FROM infrastructure_plan_reviews v
    WHERE v.resource_id = infrastructure_resources.id AND v.status = 'failed' AND v.executed_by IS NOT NULL
)`

func (r *ResourceRepository) ReviewPlan(ctx context.Context, id uuid.UUID, input model.PlanReviewInput, actor string) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	var requester, hash string
	var projectID *uuid.UUID
	var environment string
	var expiry *time.Time
	var revision time.Time
	var status model.ResourceStatus
	err = tx.QueryRow(ctx, `
		SELECT project_id, environment, status, updated_at, approval_expires_at,
		    COALESCE(CASE WHEN $2 = 'destroy' THEN destroy_requested_by ELSE requested_by END, ''),
		    COALESCE(CASE WHEN $2 = 'destroy' THEN destroy_plan_hash ELSE plan_hash END, '')
		FROM infrastructure_resources WHERE id = $1 FOR UPDATE
	`, id, input.Operation).Scan(&projectID, &environment, &status, &revision, &expiry, &requester, &hash)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrResourceNotFound
	}
	if err != nil {
		return err
	}
	if projectID == nil || requester == "" || actor == "" || hash != input.PlanHash ||
		!revision.Equal(input.Revision) || status != awaitingStatus(input.Operation) ||
		expiry == nil || !expiry.After(time.Now()) {
		return ErrResourceConflict
	}

	switch input.Action {
	case "submit":
		tag, err := tx.Exec(ctx, `
			INSERT INTO infrastructure_plan_reviews
			    (resource_id, operation, revision, plan_hash, project_id, environment, requester, submitted_by, expires_at, status)
			SELECT $1::uuid, $2::text, $3::timestamptz, $4::text, $5::uuid, $6::text, $7::text, $8::text, $9::timestamptz, 'submitted'
			WHERE $9::timestamptz > clock_timestamp()
			  AND EXISTS (SELECT 1 FROM projects WHERE id = $5)
			ON CONFLICT DO NOTHING
		`, id, input.Operation, revision, hash, projectID, environment, requester, actor, expiry)
		if err != nil {
			return err
		}
		if tag.RowsAffected() != 1 {
			return ErrResourceConflict
		}
	case "approve", "reject":
		if requester == actor {
			return ErrReviewForbidden
		}
		decision := "approved"
		if input.Action == "reject" {
			decision = "rejected"
		}
		tag, err := tx.Exec(ctx, `
			UPDATE infrastructure_plan_reviews
			SET status = $4, decided_by = $5, decided_at = clock_timestamp()
			WHERE resource_id = $1 AND operation = $2 AND revision = $3 AND status = 'submitted'
			  AND plan_hash = $6 AND project_id = $7 AND environment = $8 AND requester = $9
			  AND expires_at = $10::timestamptz AND expires_at > clock_timestamp()
			  AND ($4 <> 'approved' OR submitted_by <> $5)
		`, id, input.Operation, revision, decision, actor, hash, projectID, environment, requester, expiry)
		if err != nil {
			return err
		}
		if tag.RowsAffected() != 1 {
			return ErrResourceConflict
		}
		if input.Action == "reject" {
			next := model.ResourceStatusPending
			if input.Operation == "destroy" {
				next = model.ResourceStatusActive
			}
			if _, err := tx.Exec(ctx, `
				UPDATE infrastructure_resources
				SET status = CASE WHEN $2 = 'active' AND `+failedExecutionExists+` THEN 'destroy_failed'
                    WHEN $2 = 'pending' AND plan_started_active THEN 'active'
                    ELSE $2 END,
				    updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
				WHERE id = $1
			`, id, next); err != nil {
				return err
			}
		}
	default:
		return ErrResourceConflict
	}
	return tx.Commit(ctx)
}

func awaitingStatus(operation string) model.ResourceStatus {
	if operation == "destroy" {
		return model.ResourceStatusAwaitingDestroyApproval
	}
	return model.ResourceStatusAwaitingApproval
}

func executingStatus(operation string) model.ResourceStatus {
	if operation == "destroy" {
		return model.ResourceStatusDestroying
	}
	return model.ResourceStatusProvisioning
}

func (r *ResourceRepository) InvalidatePlan(ctx context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus) error {
	tag, err := r.pool.Exec(ctx, `
		UPDATE infrastructure_resources
		SET status = CASE WHEN $4 = 'active' AND `+failedExecutionExists+` THEN 'destroy_failed'
                WHEN $4 = 'failed' AND plan_started_active AND $3 = 'awaiting_approval' THEN 'active'
                ELSE $4 END,
		    updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
		WHERE id = $1 AND updated_at = $2 AND status = $3
	`, resource.ID, resource.UpdatedAt, awaitingStatus(operation), next)
	if err == nil && tag.RowsAffected() != 1 {
		return ErrResourceConflict
	}
	return err
}

func (r *ResourceRepository) ClaimReviewedPlan(ctx context.Context, resource model.InfrastructureResource, operation, actor string) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// Lock the resource first, consistent with submission and decision.
	var expiry time.Time
	err = tx.QueryRow(ctx, `
		SELECT approval_expires_at FROM infrastructure_resources
		WHERE id = $1 AND updated_at = $2 AND status = $3
		  AND approval_expires_at > clock_timestamp()
		FOR UPDATE
	`, resource.ID, resource.UpdatedAt, awaitingStatus(operation)).Scan(&expiry)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrResourceConflict
	}
	if err != nil {
		return err
	}
	verifiedHash := resource.PlanHash
	if operation == "destroy" {
		verifiedHash = resource.DestroyPlanHash
	}
	if actor == "" || verifiedHash == "" {
		return ErrResourceConflict
	}
	tag, err := tx.Exec(ctx, `
		UPDATE infrastructure_plan_reviews v
		SET status = 'executing', executed_by = $4, execution_started_at = clock_timestamp()
		FROM infrastructure_resources r
		WHERE v.resource_id = r.id AND r.id = $1 AND v.operation = $2 AND v.revision = $3
		  AND v.status = 'approved' AND v.decided_by <> v.requester AND v.decided_by <> v.submitted_by
		  AND v.expires_at = r.approval_expires_at
		  AND v.plan_hash = $5 AND v.plan_hash = CASE WHEN $2 = 'destroy' THEN r.destroy_plan_hash ELSE r.plan_hash END
		  AND v.requester = CASE WHEN $2 = 'destroy' THEN r.destroy_requested_by ELSE r.requested_by END
		  AND v.project_id = r.project_id AND v.environment = r.environment
		  AND EXISTS (SELECT 1 FROM projects WHERE id = v.project_id)
		  AND r.approval_expires_at > clock_timestamp()
	`, resource.ID, operation, resource.UpdatedAt, actor, verifiedHash)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrResourceConflict
	}
	if _, err := tx.Exec(ctx, `
		UPDATE infrastructure_resources SET status = $2,
		    updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
		WHERE id = $1
	`, resource.ID, executingStatus(operation)); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (r *ResourceRepository) FinishReviewedPlan(ctx context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus, succeeded bool) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	tag, err := tx.Exec(ctx, `
		UPDATE infrastructure_resources SET status = $3,
		    terraform_resource_id = COALESCE(NULLIF($4, ''), terraform_resource_id),
		    last_execution_error = $5,
		    aws_last_verified_at = COALESCE($6::timestamptz, aws_last_verified_at),
		    updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
		WHERE id = $1 AND status = $2
	`, resource.ID, executingStatus(operation), next, resource.TerraformResourceID, resource.LastExecutionError, resource.AWSLastVerifiedAt)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrResourceConflict
	}
	outcome := "failed"
	if succeeded {
		outcome = "succeeded"
	}
	tag, err = tx.Exec(ctx, `
		UPDATE infrastructure_plan_reviews SET status = $4, finished_at = clock_timestamp()
		WHERE resource_id = $1 AND operation = $2 AND revision = $3 AND status = 'executing'
	`, resource.ID, operation, resource.UpdatedAt, outcome)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return ErrResourceConflict
	}
	if succeeded && operation == "apply" && resource.ResourceType == "aws_ec2" &&
		resource.EC2Attribution != nil && resource.ProjectID != nil {
		_, err := tx.Exec(ctx, `
			INSERT INTO infrastructure_ec2_attribution
			    (resource_id, project_id, environment, region, account_id, instance_id)
			VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING
		`, resource.ID, resource.ProjectID, resource.Environment, resource.Region,
			resource.EC2Attribution.AccountID, resource.EC2Attribution.InstanceID)
		if err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}
