//go:build integration

package repository

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

// This test uses the actual public-schema definer boundaries. It requires a
// separately supplied EMPTY local test database, never an application database.
// It does not create/provision a database and is not run by offline unit tests.
func remediationPool(t *testing.T) (context.Context, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("REMEDIATION_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("empty local cloudforge_remediation_test database required")
	}
	config, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatal(err)
	}
	if config.ConnConfig.Database != "cloudforge_remediation_test" || (config.ConnConfig.Host != "localhost" && config.ConnConfig.Host != "127.0.0.1" && config.ConnConfig.Host != "::1") {
		t.Fatal("dedicated empty local test database required")
	}
	config.ConnConfig.RuntimeParams["search_path"] = "public"
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	t.Cleanup(cancel)
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	var count int
	if err = pool.QueryRow(ctx, `SELECT count(*) FROM pg_tables WHERE schemaname='public'`).Scan(&count); err != nil || count != 0 {
		t.Fatal("test database must be empty", err)
	}
	t.Cleanup(func() {
		cleanup, done := context.WithTimeout(context.Background(), 5*time.Second)
		defer done()
		_, err := pool.Exec(cleanup, `DROP SCHEMA public CASCADE; CREATE SCHEMA public`)
		if err != nil {
			t.Error(err)
		}
	})
	return ctx, pool
}

func TestClaimRemediationApproval(t *testing.T) {
	ctx, pool := remediationPool(t)
	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatal(err)
	}
	_, err := pool.Exec(ctx, `
 CREATE TABLE projects(id uuid PRIMARY KEY,created_by text);
 CREATE TABLE auth_users(username text PRIMARY KEY,role text,active boolean);
 CREATE TABLE project_members(project_id uuid,username text,level text);
 INSERT INTO auth_users VALUES('operator','platform-engineer',true);
 CREATE TABLE aiops_incidents(id varchar(64) PRIMARY KEY,status text,updated_at timestamptz);
 CREATE TABLE aiops_incident_projects(incident_id varchar(64) PRIMARY KEY REFERENCES aiops_incidents(id),project_id uuid REFERENCES projects(id));
 CREATE TABLE aiops_remediation_proposals(
 id varchar(64) PRIMARY KEY,incident_id varchar(64),target_deployment_id text,
 approved_environment text,dispatch_token_hash text,action text,status text,policy_decision text,
 policy_reason text,reason text,created_at timestamptz,proposed_by text,approved_by text,approved_role text,execution_requested_by text,
 execution_idempotency_key text,rejected_by text,rejection_reason text,rejected_at timestamptz,approved_at timestamptz,
 expires_at timestamptz,dispatch_consumed_at timestamptz);
 `)
	if err != nil {
		t.Fatal(err)
	}
	sql, err := os.ReadFile(filepath.Join("..", "..", "..", "aiops-service", "migrations", "005_remediation_reviews.sql"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = pool.Exec(ctx, string(sql)); err != nil {
		t.Fatal(err)
	}
	feedbackSQL, err := os.ReadFile(filepath.Join("..", "..", "..", "aiops-service", "migrations", "006_advisory_feedback.sql"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = pool.Exec(ctx, string(feedbackSQL)); err != nil {
		t.Fatal(err)
	}
	repo := NewDeploymentRepository(pool)
	createTarget := func() model.Deployment {
		t.Helper()
		now := time.Now().UTC()
		d := model.Deployment{ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging", Image: "nginx:stable", GitCommitSHA: "abcdef1234567", Status: model.DeploymentStatusPending, CreatedAt: now, UpdatedAt: now, CreatedBy: "proposer"}
		d.Namespace = "cf-" + d.ProjectID.String()
		if _, err := pool.Exec(ctx, `INSERT INTO projects VALUES($1,'operator')`, d.ProjectID); err != nil {
			t.Fatal(err)
		}
		if err := repo.Create(ctx, d); err != nil {
			t.Fatal(err)
		}
		return d
	}
	target, wrongTarget := createTarget(), createTarget()
	const proposal, incident, token = "proposal", "incident", "test-dispatch"
	if _, err := pool.Exec(ctx, `INSERT INTO aiops_incidents VALUES($1,'open',clock_timestamp());`, incident); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO aiops_incident_projects VALUES($1,$2)`, incident, target.ProjectID); err != nil {
		t.Fatal(err)
	}
	if err := repo.ClaimRemediation(ctx, target.ID, proposal, incident, token); !errors.Is(err, ErrRemediationApprovalRequired) {
		t.Fatalf("missing approval accepted: %v", err)
	}
	digest := fmt.Sprintf("%x", sha256.Sum256([]byte(token)))
	const insertSQL = `INSERT INTO aiops_remediation_proposals(id,incident_id,target_deployment_id,approved_environment,dispatch_token_hash,
  action,status,policy_decision,policy_reason,proposed_by,approved_by,approved_role,execution_requested_by,execution_idempotency_key,
  approved_at,expires_at,recommendation_version,project_id,resource_scope,action_fingerprint,state_snapshot)
  SELECT $1::text,$2::text,$3::text,'staging',$4::text,'rerun_deployment','EXECUTING','requires_approval','Controlled action','proposer','operator','platform-engineer','operator','claimed',
  clock_timestamp(),clock_timestamp()+interval '5 minutes',COALESCE(MAX(recommendation_version),0)+1,$5::uuid,$3::text,repeat('a',64),public.cloudforge_remediation_current_state($2::text,$3::text)
  FROM aiops_remediation_proposals`
	t.Run("fixture_insert_parameter_types", func(t *testing.T) {
		conn, err := pool.Acquire(ctx)
		if err != nil {
			t.Fatal(err)
		}
		defer conn.Release()
		description, err := conn.Conn().Prepare(ctx, "remediation_fixture_insert", insertSQL)
		if err != nil {
			t.Fatal(err)
		}
		expected := []uint32{pgtype.TextOID, pgtype.TextOID, pgtype.TextOID, pgtype.TextOID, pgtype.UUIDOID}
		if len(description.ParamOIDs) != len(expected) {
			t.Fatalf("unexpected parameter count: %v", description.ParamOIDs)
		}
		for index, oid := range expected {
			if description.ParamOIDs[index] != oid {
				t.Fatalf("parameter %d: expected OID %d, got %d", index+1, oid, description.ParamOIDs[index])
			}
		}
	})
	insert := func(id string) {
		t.Helper()
		_, err := pool.Exec(ctx, insertSQL, id, incident, target.ID.String(), digest, target.ProjectID)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := pool.Exec(ctx, `UPDATE aiops_remediation_proposals p SET approved_contract=public.cloudforge_remediation_contract(p) WHERE id=$1`, id); err != nil {
			t.Fatal(err)
		}
	}
	for i, assignment := range []string{"approved_role='sre'", "approved_by=NULL", "approved_environment='production'", "expires_at=clock_timestamp()", "status='REJECTED'", "rejected_at=clock_timestamp()", "action='rollback_deployment'", "policy_decision='blocked'", "approved_at=NULL", "parameters='{\"replicas\":2}'::jsonb"} {
		id := fmt.Sprintf("invalid-%d", i)
		insert(id)
		// Immutable-contract trigger rejection is also an expected fail-closed result.
		if _, err := pool.Exec(ctx, "UPDATE aiops_remediation_proposals SET "+assignment+" WHERE id=$1", id); err != nil {
			continue
		}
		if err := repo.ClaimRemediation(ctx, target.ID, id, incident, token); !errors.Is(err, ErrRemediationApprovalRequired) {
			t.Fatalf("invalid approval accepted: %s: %v", assignment, err)
		}
		// Rejected historical effects intentionally suppress subsequent reruns. Keep
		// invalid fixtures separate from the final valid concurrent-claim scenario.
		if _, err := pool.Exec(ctx, `DELETE FROM aiops_remediation_proposals WHERE id=$1`, id); err != nil {
			t.Fatal(err)
		}
	}
	insert(proposal)
	for _, err := range []error{repo.ClaimRemediation(ctx, wrongTarget.ID, proposal, incident, token), repo.ClaimRemediation(ctx, target.ID, proposal, "wrong-incident", token), repo.ClaimRemediation(ctx, target.ID, proposal, incident, "forged")} {
		if !errors.Is(err, ErrRemediationApprovalRequired) {
			t.Fatalf("mismatched approval accepted: %v", err)
		}
	}
	wins := 0
	for _, err := range concurrentWrites(2, func() error { return repo.ClaimRemediation(ctx, target.ID, proposal, incident, token) }) {
		if err == nil {
			wins++
		} else if !errors.Is(err, ErrRemediationApprovalRequired) {
			t.Fatal(err)
		}
	}
	if wins != 1 {
		t.Fatalf("expected one claim, got %d", wins)
	}
	if err := repo.ClaimRemediation(ctx, target.ID, proposal, incident, token); !errors.Is(err, ErrRemediationApprovalRequired) {
		t.Fatalf("replay accepted: %v", err)
	}
}
