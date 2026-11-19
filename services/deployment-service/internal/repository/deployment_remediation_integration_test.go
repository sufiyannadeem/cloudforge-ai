//go:build integration

package repository

import (
	"crypto/sha256"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

func TestClaimRemediationApproval(t *testing.T) {
	ctx, pool := newIsolatedDeploymentTestPool(t)
	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `
		CREATE TABLE aiops_remediation_proposals (
			id text PRIMARY KEY, incident_id text, target_deployment_id text,
			approved_environment text, dispatch_token_hash text, action text,
			status text, policy_decision text, approved_by text, approved_role text,
			execution_idempotency_key text, rejected_at timestamptz, approved_at timestamptz,
			expires_at timestamptz, dispatch_consumed_at timestamptz
		)
	`); err != nil {
		t.Fatal(err)
	}
	repo := NewDeploymentRepository(pool)
	createTarget := func() uuid.UUID {
		t.Helper()
		now := time.Now().UTC()
		d := model.Deployment{
			ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging",
			Image: "nginx:stable", GitCommitSHA: "abcdef1234567", Namespace: "test",
			Status: model.DeploymentStatusPending, CreatedAt: now, UpdatedAt: now,
		}
		if err := repo.Create(ctx, d); err != nil {
			t.Fatal(err)
		}
		return d.ID
	}

	target, wrongTarget := createTarget(), createTarget()
	const proposal, incident, token = "proposal", "incident", "test-dispatch"
	if err := repo.ClaimRemediation(ctx, target, proposal, incident, token); !errors.Is(err, ErrRemediationApprovalRequired) {
		t.Fatalf("missing approval accepted: %v", err)
	}
	digest := fmt.Sprintf("%x", sha256.Sum256([]byte(token)))
	const insert = `
		INSERT INTO aiops_remediation_proposals VALUES (
			$1, $2, $3, 'staging', $4, 'rerun_deployment', 'EXECUTING',
			'requires_approval', 'operator', 'sre', 'claimed', NULL,
			clock_timestamp(), clock_timestamp() + interval '5 minutes', NULL
		)
	`
	for i, assignment := range []string{
		"approved_role = 'admin'", "approved_by = NULL", "approved_environment = 'production'",
		"expires_at = clock_timestamp()", "status = 'REJECTED'", "rejected_at = clock_timestamp()",
		"action = 'rollback_deployment'", "policy_decision = 'blocked'", "approved_at = NULL",
	} {
		id := fmt.Sprintf("invalid-%d", i)
		if _, err := pool.Exec(ctx, insert, id, incident, target.String(), digest); err != nil {
			t.Fatal(err)
		}
		if _, err := pool.Exec(ctx, "UPDATE aiops_remediation_proposals SET "+assignment+" WHERE id = $1", id); err != nil {
			t.Fatal(err)
		}
		if err := repo.ClaimRemediation(ctx, target, id, incident, token); !errors.Is(err, ErrRemediationApprovalRequired) {
			t.Fatalf("invalid approval (%s) accepted: %v", assignment, err)
		}
	}
	if _, err := pool.Exec(ctx, insert, proposal, incident, target.String(), digest); err != nil {
		t.Fatal(err)
	}
	for _, err := range []error{
		repo.ClaimRemediation(ctx, wrongTarget, proposal, incident, token),
		repo.ClaimRemediation(ctx, target, proposal, "wrong-incident", token),
		repo.ClaimRemediation(ctx, target, proposal, incident, "forged-dispatch"),
	} {
		if !errors.Is(err, ErrRemediationApprovalRequired) {
			t.Fatalf("mismatched approval accepted: %v", err)
		}
	}

	wins := 0
	for _, err := range concurrentWrites(2, func() error {
		return repo.ClaimRemediation(ctx, target, proposal, incident, token)
	}) {
		if err == nil {
			wins++
		} else if !errors.Is(err, ErrRemediationApprovalRequired) {
			t.Fatal(err)
		}
	}
	if wins != 1 {
		t.Fatalf("expected a single successful claim, got %d", wins)
	}
	queued, err := repo.GetByID(ctx, target)
	if err != nil || queued.Status != model.DeploymentStatusQueued {
		t.Fatalf("expected queued deployment, got %s: %v", queued.Status, err)
	}
	if err := repo.ReleaseQueuedDeployment(ctx, target, time.Now()); err != nil {
		t.Fatal(err)
	}
	if err := repo.ClaimRemediation(ctx, target, proposal, incident, token); !errors.Is(err, ErrRemediationApprovalRequired) {
		t.Fatalf("approval replay accepted on pending deployment: %v", err)
	}
}
