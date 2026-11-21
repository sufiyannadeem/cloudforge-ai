package repository

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"time"
)

var ErrDriftReviewRequired = errors.New("scheduled drift batch requires review or evidence is unavailable")

func scheduledEvidence(raw json.RawMessage, observation error) (DriftScan, bool) {
	scan := DriftScan{Actor: "service:drift-scheduler", Status: "observed", Findings: raw}
	var findings []json.RawMessage
	if observation != nil || len(raw) == 0 || string(raw) == "null" || json.Unmarshal(raw, &findings) != nil {
		scan.Status = "unavailable"
		scan.Findings = json.RawMessage("[]")
		return scan, true
	}
	return scan, len(findings) > 0
}

// ScheduledDrift reuses the existing read-only observer and optimistic history
// insert. The transaction advisory lock prevents overlapping scheduler instances.
func (r *ResourceRepository) ScheduledDrift(ctx context.Context, observe func(context.Context, model.InfrastructureResource) (json.RawMessage, error)) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() {
		rollback, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = tx.Rollback(rollback)
	}()
	var owned bool
	if err = tx.QueryRow(ctx, "SELECT pg_try_advisory_xact_lock(719920526399)").Scan(&owned); err != nil {
		return err
	}
	if !owned {
		return ErrDriftReviewRequired
	}
	rows, err := tx.Query(ctx, `SELECT r.id FROM infrastructure_resources r WHERE r.status='active'
 ORDER BY (SELECT max(scanned_at) FROM terraform_drift_scans d WHERE d.resource_id=r.id) ASC NULLS FIRST,r.id LIMIT 5`)
	if err != nil {
		return err
	}
	ids := []uuid.UUID{}
	for rows.Next() {
		var id uuid.UUID
		if err = rows.Scan(&id); err != nil {
			rows.Close()
			return err
		}
		ids = append(ids, id)
	}
	rows.Close()
	if err = rows.Err(); err != nil {
		return err
	}
	review := false
	for _, id := range ids {
		resource, err := r.GetByID(ctx, id)
		if err != nil {
			return err
		}
		raw, observation := observe(ctx, resource)
		scan, needsReview := scheduledEvidence(raw, observation)
		review = review || needsReview
		if err = r.pool.QueryRow(ctx, "SELECT id,scanned_at FROM public.cloudforge_record_scheduled_drift($1,$2,$3,$4::jsonb)", id, resource.UpdatedAt, scan.Status, scan.Findings).Scan(&scan.ID, &scan.ScannedAt); err != nil {
			return ErrDriftReviewRequired
		}
	}
	if err = tx.Commit(ctx); err != nil {
		return err
	}
	if review {
		return ErrDriftReviewRequired
	}
	return nil
}
