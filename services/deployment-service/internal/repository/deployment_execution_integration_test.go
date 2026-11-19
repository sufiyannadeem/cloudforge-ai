//go:build integration

package repository

import (
	"context"
	"encoding/json"
	"errors"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func newIsolatedDeploymentTestPool(t *testing.T) (context.Context, *pgxpool.Pool) {
	t.Helper()
	url := os.Getenv("DATABASE_URL")
	if url == "" {
		t.Skip("DATABASE_URL is required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		t.Fatal("invalid test database URL")
	}
	admin, err := pgxpool.NewWithConfig(ctx, config.Copy())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(admin.Close)
	schema := pgx.Identifier{"deployment_test_" + uuid.New().String()}.Sanitize()
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		cleanup, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if _, err := admin.Exec(cleanup, "DROP SCHEMA "+schema+" CASCADE"); err != nil {
			t.Error(err)
		}
	})
	config.ConnConfig.RuntimeParams["search_path"] = schema
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	return ctx, pool
}

func TestExecutionLeaseRecovery(t *testing.T) {
	for _, mode := range []string{"simulated", "kubernetes"} {
		t.Run(mode, func(t *testing.T) { testExecutionLeaseRecovery(t, mode) })
	}
}

func testExecutionLeaseRecovery(t *testing.T, mode string) {
	ctx, pool := newIsolatedDeploymentTestPool(t)
	for _, err := range concurrentWrites(2, func() error { return migration.NewRunner(pool).Run(ctx) }) {
		if err != nil {
			t.Fatal(err)
		}
	}

	now := time.Now().UTC()
	deployment := model.Deployment{
		ID: uuid.New(), ProjectID: uuid.New(), Environment: "development",
		Image: "nginx:stable", GitCommitSHA: "abcdef1234567", Namespace: "test",
		Status: model.DeploymentStatusPending, CreatedAt: now, UpdatedAt: now,
	}
	if _, err := pool.Exec(ctx, `
		CREATE TABLE projects (id uuid PRIMARY KEY, created_by text);
		CREATE TABLE project_members (project_id uuid, username text, level text)
	`); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, "INSERT INTO projects VALUES ($1, 'owner')", deployment.ProjectID); err != nil {
		t.Fatal(err)
	}
	deployment.Namespace = identity.ProjectNamespace(deployment.ProjectID.String())
	repo := NewDeploymentRepository(pool)
	if err := repo.Create(ctx, deployment); err != nil {
		t.Fatal(err)
	}
	access := identity.ProjectAccess{DB: pool}
	for _, tc := range []struct {
		subject, role string
		allowed       bool
	}{
		{"owner", "developer", true},
		{"unrelated", "developer", false},
		{"operator", "platform-engineer", true},
		{"reliability", "sre", true},
	} {
		req := identity.WithClaims(httptest.NewRequest("GET", "/", nil), identity.Claims{
			Issuer: "frontend", Subject: tc.subject, Role: tc.role,
		})
		accessErr := access.Resource(req.Context(), "deployment", deployment.ID.String(), false)
		if (tc.allowed && accessErr != nil) || (!tc.allowed && !errors.Is(accessErr, identity.ErrProjectHidden)) {
			t.Fatalf("unexpected project access for %s: %v", tc.subject, accessErr)
		}
		list, err := repo.List(req.Context(), 10, 0)
		if err != nil || (len(list) != 0) != tc.allowed {
			t.Fatalf("unexpected deployment visibility for %s: %d rows, %v", tc.subject, len(list), err)
		}
	}
	if err := repo.ClaimPendingDeployment(ctx, deployment.ID, now); err != nil {
		t.Fatal(err)
	}

	// A new repository instance claims work submitted before restart.
	other := NewDeploymentRepository(pool)
	repo.SetExecutionMode(mode)
	other.SetExecutionMode(mode)
	const ttl = 30 * time.Second
	first, err := other.ClaimExecution(ctx, ttl)
	if err != nil || first.DeploymentID != deployment.ID || first.Reconcile {
		t.Fatalf("unexpected initial claim: %+v, %v", first, err)
	}
	current, err := repo.GetByID(ctx, deployment.ID)
	if err != nil {
		t.Fatal(err)
	}
	if current.ExecutionMode != mode {
		t.Fatalf("expected %s deployment, got %q", mode, current.ExecutionMode)
	}
	changed := current
	changed.Image = "nginx:latest"
	if err := repo.Update(ctx, changed, current); !errors.Is(err, ErrDeploymentConflict) {
		t.Fatalf("execution configuration could be overwritten while leased: %v", err)
	}
	expire := func() {
		t.Helper()
		if _, err := pool.Exec(ctx, "UPDATE deployments SET execution_expires_at = clock_timestamp() - interval '1 second' WHERE id = $1", deployment.ID); err != nil {
			t.Fatal(err)
		}
	}
	expire()
	if err := other.BeginExecution(ctx, first); !errors.Is(err, ErrExecutionLeaseLost) {
		t.Fatalf("expired worker admitted to execution: %v", err)
	}
	if err := other.RenewExecution(ctx, first, ttl); !errors.Is(err, ErrExecutionLeaseLost) {
		t.Fatalf("expired worker renewed lease: %v", err)
	}

	second, err := repo.ClaimExecution(ctx, ttl)
	if err != nil || second.Token == uuid.Nil || second.Token == first.Token || second.Reconcile {
		t.Fatalf("expected safe retry after pre-mutation crash: %+v, %v", second, err)
	}
	if err := repo.RenewExecution(ctx, second, 2*ttl); err != nil {
		t.Fatal(err)
	}
	var extended bool
	if err := pool.QueryRow(ctx, "SELECT execution_expires_at > clock_timestamp() + interval '30 seconds' FROM deployments WHERE id = $1", deployment.ID).Scan(&extended); err != nil || !extended {
		t.Fatalf("lease expiry was not extended: %v", err)
	}
	if err := repo.BeginExecution(ctx, second); err != nil {
		t.Fatal(err)
	}
	expire()

	type claimResult struct {
		lease ExecutionLease
		err   error
	}
	results := make(chan claimResult, 2)
	start := make(chan struct{})
	for _, contender := range []*DeploymentRepository{repo, other} {
		go func() {
			<-start
			lease, err := contender.ClaimExecution(ctx, ttl)
			results <- claimResult{lease, err}
		}()
	}
	close(start)
	var winner ExecutionLease
	for range 2 {
		result := <-results
		if result.err != nil {
			t.Fatal(result.err)
		}
		if result.lease.Token != uuid.Nil {
			if winner.Token != uuid.Nil || !result.lease.Reconcile || result.lease.DeploymentID != deployment.ID {
				t.Fatalf("unexpected recovery claim: %+v", result.lease)
			}
			winner = result.lease
		}
	}
	if winner.Token == uuid.Nil {
		t.Fatal("recovery had no owner")
	}
	if err := repo.FinishExecution(ctx, second, nil); !errors.Is(err, ErrExecutionLeaseLost) {
		t.Fatalf("stale worker could finalize: %v", err)
	}
	if err := repo.FinishExecution(ctx, winner, nil); err != nil {
		t.Fatal(err)
	}
	attempts, err := NewDeploymentAttemptRepository(pool)
	if err != nil {
		t.Fatal(err)
	}
	history, err := attempts.ListByDeploymentID(ctx, deployment.ID, 10, 0)
	if err != nil || len(history) != 3 {
		t.Fatalf("unexpected attempt history length %d: %v", len(history), err)
	}
	for _, attempt := range history {
		expected := model.AttemptStatusFailed
		if attempt.ID == winner.Token {
			expected = model.AttemptStatusSucceeded
		}
		if attempt.Status != expected || attempt.CompletedAt == nil || attempt.ExecutionMode != mode {
			t.Fatalf("incorrect completion for attempt %d", attempt.AttemptNumber)
		}
	}
}

func TestKubernetesRollbackUsesEarlierImmutableReleaseInSameNamespace(t *testing.T) {
	ctx, pool := newIsolatedDeploymentTestPool(t)
	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatal(err)
	}
	repo := NewDeploymentRepository(pool)
	repo.SetExecutionMode("kubernetes")
	now := time.Now().UTC()
	project := uuid.New()
	namespace := identity.ProjectNamespace(project.String())
	digest := "registry.example/app@sha256:" + strings.Repeat("a", 64)
	create := func(offset time.Duration, ns, image, mode string, status model.DeploymentStatus) uuid.UUID {
		t.Helper()
		id := uuid.New()
		deployment := model.Deployment{ID: id, ProjectID: project, Namespace: ns, Environment: "production",
			Image: image, GitCommitSHA: "abcdef1234567", Status: status,
			CreatedAt: now.Add(offset), UpdatedAt: now.Add(offset)}
		if err := repo.Create(ctx, deployment); err != nil {
			t.Fatal(err)
		}
		if _, err := pool.Exec(ctx, "UPDATE deployments SET execution_mode = $2 WHERE id = $1", id, mode); err != nil {
			t.Fatal(err)
		}
		return id
	}

	good := create(-5*time.Minute, namespace, digest, "kubernetes", model.DeploymentStatusSucceeded)
	create(-4*time.Minute, namespace, digest, "simulated", model.DeploymentStatusSucceeded)
	create(-3*time.Minute, "elsewhere", digest, "kubernetes", model.DeploymentStatusSucceeded)
	create(-2*time.Minute, namespace, "registry.example/app:latest", "kubernetes", model.DeploymentStatusSucceeded)
	create(-time.Minute, namespace, digest, "unknown", model.DeploymentStatusSucceeded)
	current := create(0, namespace, digest, "kubernetes", model.DeploymentStatusFailed)
	create(time.Minute, namespace, digest, "kubernetes", model.DeploymentStatusSucceeded)
	got, err := repo.GetPreviousSuccessfulDeployment(ctx, project, "production", current)
	if err != nil || got.ID != good {
		t.Fatalf("rollback selected an unsafe source: %s, %v", got.ID, err)
	}
	evidence := json.RawMessage(`{"source":"live_kubernetes","severity":"warning"}`)
	capture, err := repo.SaveDiagnostic(ctx, good, "developer", evidence)
	if err != nil || capture.CapturedAt.IsZero() {
		t.Fatalf("diagnostic audit record not saved: %v", err)
	}
	history, err := repo.DiagnosticHistory(ctx, good)
	if err != nil || len(history) != 1 || history[0].Actor != "developer" || history[0].ID != capture.ID {
		t.Fatalf("diagnostic capture not returned by deployment-scoped history: %v", err)
	}
	foreign, err := repo.DiagnosticHistory(ctx, current)
	if err != nil || len(foreign) != 0 {
		t.Fatalf("diagnostic audit crossed deployment boundaries: %v", err)
	}
	if err := repo.Delete(ctx, good); !errors.Is(err, ErrDeploymentConflict) {
		t.Fatalf("Kubernetes execution history was eligible for deletion: %v", err)
	}
	pending := create(2*time.Minute, namespace, digest, "unknown", model.DeploymentStatusPending)
	if err := repo.Delete(ctx, pending); err != nil {
		t.Fatalf("pending record could not be removed: %v", err)
	}
}
