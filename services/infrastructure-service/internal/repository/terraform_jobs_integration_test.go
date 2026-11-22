//go:build integration

package repository

import (
	"context"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func TestTerraformJobDurabilityClaimAndNoReplay(t *testing.T) {
	dsn := os.Getenv("CLOUDFORGE_JOB_TEST_DSN")
	if dsn == "" {
		t.Skip("dedicated isolated job fixture required")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	schema := "jobs_" + uuid.NewString()[:8]
	if _, err = pool.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	defer pool.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatal(err)
	}
	cfg.ConnConfig.RuntimeParams["search_path"] = schema
	db, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err = db.Exec(ctx, "CREATE TABLE infrastructure_resources(id uuid PRIMARY KEY)"); err != nil {
		t.Fatal(err)
	}
	sql, err := os.ReadFile(filepath.Join("..", "migration", "migrations", "013_terraform_jobs.sql"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(ctx, string(sql)); err != nil {
		t.Fatal(err)
	}
	r := NewResourceRepository(db)
	id := uuid.New()
	if _, err = db.Exec(ctx, "INSERT INTO infrastructure_resources VALUES($1)", id); err != nil {
		t.Fatal(err)
	}
	j := TerraformJob{ID: uuid.New(), ResourceID: id, Path: "/api/v1/resources/" + id.String() + "/apply", Body: []byte(`{"plan_hash":"reviewed"}`), Claims: identity.Claims{Role: "platform-engineer", Subject: "operator"}}
	if err = r.EnqueueTerraformJob(ctx, j); err != nil {
		t.Fatal(err)
	}
	duplicate := j
	duplicate.ID = uuid.New()
	if r.EnqueueTerraformJob(ctx, duplicate) == nil {
		t.Fatal("overlapping job accepted")
	}
	var wg sync.WaitGroup
	var mu sync.Mutex
	claims := 0
	for range 4 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if got, e := r.ClaimTerraformJob(ctx); e == nil {
				mu.Lock()
				claims++
				mu.Unlock()
				if got.Claims.Subject != "operator" {
					t.Error("identity lost")
				}
			}
		}()
	}
	wg.Wait()
	if claims != 1 {
		t.Fatalf("claimed %d times", claims)
	}
	if err = r.FinishTerraformJob(ctx, j.ID, 200, []byte(`{"status":"active"}`)); err != nil {
		t.Fatal(err)
	}
	got, err := r.GetTerraformJob(ctx, id, j.ID)
	if err != nil || got.Status != "succeeded" {
		t.Fatal("completion not durable", err)
	}
	j.ID = uuid.New()
	if err = r.EnqueueTerraformJob(ctx, j); err != nil {
		t.Fatal(err)
	}
	if _, err = r.ClaimTerraformJob(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(ctx, "UPDATE infrastructure_jobs SET deadline=clock_timestamp()-interval '1 second' WHERE id=$1", j.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = r.ClaimTerraformJob(ctx); err == nil {
		t.Fatal("abandoned mutation replayed")
	}
	got, err = r.GetTerraformJob(ctx, id, j.ID)
	if err != nil || got.Status != "interrupted" {
		t.Fatal("abandoned work not marked uncertain")
	}
	if r.FinishTerraformJob(ctx, j.ID, 200, []byte(`{}`)) == nil {
		t.Fatal("stale completion accepted")
	}
}
