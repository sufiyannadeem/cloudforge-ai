package repository

import (
	"context"
	"encoding/json"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type TerraformJob struct {
	ID           uuid.UUID       `json:"id"`
	ResourceID   uuid.UUID       `json:"resource_id"`
	Status       string          `json:"status"`
	Response     json.RawMessage `json:"response,omitempty"`
	ResponseCode *int            `json:"response_code,omitempty"`
	Path         string          `json:"-"`
	Body         []byte          `json:"-"`
	Claims       identity.Claims `json:"-"`
}

func (r *ResourceRepository) EnqueueTerraformJob(ctx context.Context, j TerraformJob) error {
	claims, err := json.Marshal(j.Claims)
	if err != nil {
		return err
	}
	_, err = r.pool.Exec(ctx, `INSERT INTO infrastructure_jobs(id,resource_id,path,body,claims) VALUES($1,$2,$3,$4,$5)`, j.ID, j.ResourceID, j.Path, j.Body, claims)
	return err
}

func (r *ResourceRepository) GetTerraformJob(ctx context.Context, resourceID, id uuid.UUID) (TerraformJob, error) {
	var j TerraformJob
	err := r.pool.QueryRow(ctx, `SELECT id,resource_id,
 CASE WHEN status IN ('queued','running') AND deadline<clock_timestamp() THEN 'interrupted' ELSE status END,
 response,response_code FROM infrastructure_jobs WHERE id=$1 AND resource_id=$2`, id, resourceID).Scan(&j.ID, &j.ResourceID, &j.Status, &j.Response, &j.ResponseCode)
	return j, err
}

func (r *ResourceRepository) ClaimTerraformJob(ctx context.Context) (TerraformJob, error) {
	// Abandoned mutations require operator reconciliation, never automatic retry.
	_, err := r.pool.Exec(ctx, `UPDATE infrastructure_jobs SET status='interrupted' WHERE status IN ('queued','running') AND deadline < clock_timestamp()`)
	if err != nil {
		return TerraformJob{}, err
	}
	var j TerraformJob
	var claims []byte
	err = r.pool.QueryRow(ctx, `UPDATE infrastructure_jobs SET status='running',deadline=clock_timestamp()+interval '40 minutes'
 WHERE id=(SELECT id FROM infrastructure_jobs WHERE status='queued' AND deadline>clock_timestamp() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
 RETURNING id,resource_id,path,body,claims,status`).Scan(&j.ID, &j.ResourceID, &j.Path, &j.Body, &claims, &j.Status)
	if err != nil {
		return j, err
	}
	err = json.Unmarshal(claims, &j.Claims)
	return j, err
}

func (r *ResourceRepository) FinishTerraformJob(ctx context.Context, id uuid.UUID, code int, body []byte) error {
	status := "failed"
	if code >= 200 && code < 300 {
		status = "succeeded"
	}
	tag, err := r.pool.Exec(ctx, `UPDATE infrastructure_jobs SET status=$2,response_code=$3,response=$4
 WHERE id=$1 AND status='running' AND deadline>clock_timestamp()`, id, status, code, body)
	if err == nil && tag.RowsAffected() != 1 {
		return pgx.ErrNoRows
	}
	return err
}
