package repository

import (
	"context"
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

type DiagnosticCapture struct {
	ID         uuid.UUID       `json:"id"`
	Actor      string          `json:"actor"`
	CapturedAt time.Time       `json:"captured_at"`
	Evidence   json.RawMessage `json:"evidence"`
}

func (r *DeploymentRepository) SaveDiagnostic(ctx context.Context, deploymentID uuid.UUID, actor string, evidence json.RawMessage) (DiagnosticCapture, error) {
	capture := DiagnosticCapture{ID: uuid.New(), Actor: actor, Evidence: evidence}
	err := r.pool.QueryRow(ctx, `
		INSERT INTO deployment_diagnostics (id, deployment_id, actor, evidence)
		VALUES ($1, $2, $3, $4)
		RETURNING captured_at
	`, capture.ID, deploymentID, actor, evidence).Scan(&capture.CapturedAt)
	return capture, err
}

func (r *DeploymentRepository) DiagnosticHistory(ctx context.Context, deploymentID uuid.UUID) ([]DiagnosticCapture, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id, actor, captured_at, evidence FROM deployment_diagnostics
		WHERE deployment_id = $1 ORDER BY captured_at DESC, id DESC LIMIT 10
	`, deploymentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []DiagnosticCapture{}
	for rows.Next() {
		var item DiagnosticCapture
		if err := rows.Scan(&item.ID, &item.Actor, &item.CapturedAt, &item.Evidence); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}
