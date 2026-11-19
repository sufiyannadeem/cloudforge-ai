package repository

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

type DriftScan struct {
	ID        int64           `json:"id"`
	Actor     string          `json:"actor"`
	Status    string          `json:"status"`
	Findings  json.RawMessage `json:"findings"`
	ScannedAt time.Time       `json:"scanned_at"`
}

func (r *ResourceRepository) RecordDrift(ctx context.Context, id uuid.UUID, revision time.Time, scan DriftScan) (DriftScan, error) {
	err := r.pool.QueryRow(ctx, `
		INSERT INTO terraform_drift_scans (resource_id, actor, status, findings)
		SELECT id, $3, $4, $5 FROM infrastructure_resources
		WHERE id = $1 AND updated_at = $2 AND status = 'active'
		FOR UPDATE
		RETURNING id, scanned_at`, id, revision, scan.Actor, scan.Status, scan.Findings).Scan(&scan.ID, &scan.ScannedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return DriftScan{}, ErrResourceConflict
	}
	return scan, err
}

func (r *ResourceRepository) DriftHistory(ctx context.Context, id uuid.UUID) ([]DriftScan, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id, actor, status, findings, scanned_at FROM terraform_drift_scans
		WHERE resource_id = $1 ORDER BY id DESC LIMIT 10`, id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	history := []DriftScan{}
	for rows.Next() {
		var scan DriftScan
		if err := rows.Scan(&scan.ID, &scan.Actor, &scan.Status, &scan.Findings, &scan.ScannedAt); err != nil {
			return nil, err
		}
		history = append(history, scan)
	}
	return history, rows.Err()
}
