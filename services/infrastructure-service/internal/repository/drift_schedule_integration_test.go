//go:build integration

package repository

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"os"
	"testing"
	"time"
)

func TestScheduledDriftDatabaseBoundary(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	pool, err := pgxpool.New(ctx, os.Getenv("DATABASE_URL"))
	if err != nil {
		t.Fatal("fixture DB unavailable")
	}
	defer pool.Close()
	var proof string
	if err = pool.QueryRow(ctx, "SELECT proof FROM database_boundary_fixture WHERE id=$1", os.Getenv("CF_DB_FIXTURE_ID")).Scan(&proof); err != nil || proof != os.Getenv("CF_DB_FIXTURE_PROOF") || proof == "" {
		t.Fatal("disposable fixture proof required")
	}
	id := uuid.New()
	_, err = testPool.Exec(ctx, `INSERT INTO infrastructure_resources(id,name,provider,region,environment,status,terraform_directory,resource_type)
 VALUES ($1,'cf-drift-fixture','aws','eu-west-1','development','active','/synthetic/no-execution','aws_ec2')`, id)
	if err != nil {
		t.Fatal(err)
	}
	defer testPool.Exec(context.Background(), "DELETE FROM terraform_drift_scans WHERE resource_id=$1", id)
	repo := NewResourceRepository(pool)
	observer := func(context.Context, model.InfrastructureResource) (json.RawMessage, error) {
		return json.RawMessage(`[{"source":"provider_drift","severity":"high"}]`), nil
	}
	if err = repo.ScheduledDrift(ctx, observer); !errors.Is(err, ErrDriftReviewRequired) {
		t.Fatalf("findings must require review: %v", err)
	}
	history, err := repo.DriftHistory(ctx, id)
	if err != nil || len(history) != 1 || history[0].Actor != "service:drift-scheduler" || history[0].Status != "observed" {
		t.Fatal("scheduled history missing")
	}
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(719920526399)"); err != nil {
		t.Fatal(err)
	}
	called := false
	err = repo.ScheduledDrift(ctx, func(context.Context, model.InfrastructureResource) (json.RawMessage, error) {
		called = true
		return nil, nil
	})
	tx.Rollback(ctx)
	if !errors.Is(err, ErrDriftReviewRequired) || called {
		t.Fatal("overlapping observer ran")
	}
	err = repo.ScheduledDrift(ctx, func(context.Context, model.InfrastructureResource) (json.RawMessage, error) {
		return nil, errors.New("unavailable")
	})
	history, _ = repo.DriftHistory(ctx, id)
	if !errors.Is(err, ErrDriftReviewRequired) || len(history) != 2 || history[0].Status != "unavailable" {
		t.Fatal("provider outage was hidden")
	}
	err = repo.ScheduledDrift(ctx, func(context.Context, model.InfrastructureResource) (json.RawMessage, error) {
		_, e := testPool.Exec(ctx, "UPDATE infrastructure_resources SET status='inactive' WHERE id=$1", id)
		return json.RawMessage("[]"), e
	})
	history, _ = repo.DriftHistory(ctx, id)
	if !errors.Is(err, ErrDriftReviewRequired) || len(history) != 2 {
		t.Fatal("stale scheduled evidence persisted")
	}
}
