//go:build integration

package repository

import (
	"context"
	"errors"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func TestStrategyPersistenceAndIndependentPromotion(t *testing.T) {
	ctx, pool := newIsolatedDeploymentTestPool(t)
	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatal(err)
	}
	authSQL, err := os.ReadFile("../../../project-service/internal/migration/migrations/002_create_auth_accounts.sql")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = pool.Exec(ctx, string(authSQL)); err != nil {
		t.Fatal(err)
	}
	_, err = pool.Exec(ctx, `INSERT INTO auth_users(username,role,password_hash,password_salt) VALUES ('requester','platform-engineer',decode(repeat('00',32),'hex'),decode(repeat('00',32),'hex')),('reviewer','platform-engineer',decode(repeat('00',32),'hex'),decode(repeat('00',32),'hex')),('outsider','developer',decode(repeat('00',32),'hex'),decode(repeat('00',32),'hex'))`)
	if err != nil {
		t.Fatal(err)
	}
	repo := NewDeploymentRepository(pool)
	repo.SetExecutionMode("kubernetes")
	d := model.Deployment{ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging", Image: "ghcr.io/example/app@sha256:" + strings.Repeat("a", 64), GitCommitSHA: "abcdef1", Status: model.DeploymentStatusPending, CreatedAt: time.Now(), UpdatedAt: time.Now(), Strategy: model.DeploymentStrategy{Type: "blue-green"}, CreatedBy: "requester"}
	d.Namespace = "cf-" + d.ProjectID.String()
	if err := repo.Create(ctx, d); err != nil {
		t.Fatal(err)
	}
	got, err := repo.GetByID(ctx, d.ID)
	if err != nil || got.Strategy.Type != "blue-green" || got.CreatedBy != "requester" {
		t.Fatal(got, err)
	}
	if err := repo.ClaimPendingDeployment(ctx, d.ID, time.Now()); err != nil {
		t.Fatal(err)
	}
	lease, err := repo.ClaimExecution(ctx, time.Minute)
	if err != nil || lease.DeploymentID != d.ID {
		t.Fatal(lease, err)
	}
	claimCtx := func(actor string) context.Context {
		req := httptest.NewRequest("POST", "/", nil).WithContext(ctx)
		return identity.WithClaims(req, identity.Claims{Issuer: "frontend", Subject: actor, Role: "platform-engineer", Expiry: time.Now().Unix() + 25, Nonce: uuid.NewString()}).Context()
	}
	for _, actor := range []string{"requester", "outsider"} {
		if _, err := repo.ClaimPromotion(claimCtx(actor), d.ID, "uid", "42"); !errors.Is(err, ErrPromotionDenied) {
			t.Fatal("self/unprivileged approval accepted", err)
		}
	}
	if _, err := pool.Exec(ctx, `UPDATE auth_users SET active=false WHERE username='reviewer'`); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.ClaimPromotion(claimCtx("reviewer"), d.ID, "uid", "42"); !errors.Is(err, ErrPromotionDenied) {
		t.Fatal("deactivated approver accepted", err)
	}
	if _, err := pool.Exec(ctx, `UPDATE auth_users SET active=true,role='sre' WHERE username='reviewer'`); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.ClaimPromotion(claimCtx("reviewer"), d.ID, "uid", "42"); !errors.Is(err, ErrPromotionDenied) {
		t.Fatal("stale administrator privileges accepted", err)
	}
	if _, err := pool.Exec(ctx, `UPDATE auth_users SET role='platform-engineer' WHERE username='reviewer'`); err != nil {
		t.Fatal(err)
	}
	var group sync.WaitGroup
	var mu sync.Mutex
	success := 0
	for range 8 {
		group.Add(1)
		go func() {
			defer group.Done()
			id, err := repo.ClaimPromotion(claimCtx("reviewer"), d.ID, "uid", "42")
			if err == nil {
				mu.Lock()
				success++
				mu.Unlock()
				if err := repo.CompletePromotion(ctx, id, true); err != nil {
					t.Error(err)
				}
			} else if !errors.Is(err, ErrPromotionDenied) {
				t.Error(err)
			}
		}()
	}
	group.Wait()
	if success != 1 {
		t.Fatal(success)
	}
	history, err := repo.PromotionHistory(ctx, d.ID)
	if err != nil || len(history) != 1 || history[0].Outcome != "submitted" || !strings.Contains(string(history[0].Binding), d.Image) {
		t.Fatal(history, err)
	}
	if _, err := repo.ClaimPromotion(claimCtx("reviewer"), d.ID, "uid", "42"); !errors.Is(err, ErrPromotionDenied) {
		t.Fatal("replay accepted", err)
	}
}
func TestDifferentDeploymentRowsCannotExecuteSameWorkload(t *testing.T) {
	ctx, pool := newIsolatedDeploymentTestPool(t)
	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatal(err)
	}
	repo := NewDeploymentRepository(pool)
	repo.SetExecutionMode("kubernetes")
	project := uuid.New()
	for range 2 {
		d := model.Deployment{ID: uuid.New(), ProjectID: project, Namespace: "cf-" + project.String(), Environment: "staging", Image: "image", GitCommitSHA: "abcdef1", Status: model.DeploymentStatusQueued, CreatedAt: time.Now(), UpdatedAt: time.Now()}
		if err := repo.Create(ctx, d); err != nil {
			t.Fatal(err)
		}
	}
	var group sync.WaitGroup
	leases := make(chan ExecutionLease, 2)
	for range 2 {
		group.Add(1)
		go func() {
			defer group.Done()
			lease, err := repo.ClaimExecution(ctx, time.Minute)
			if err != nil {
				t.Error(err)
			}
			if lease.Token != uuid.Nil {
				leases <- lease
			}
		}()
	}
	group.Wait()
	close(leases)
	claimed := []ExecutionLease{}
	for lease := range leases {
		claimed = append(claimed, lease)
	}
	if len(claimed) != 1 {
		t.Fatal("concurrent workload leases", len(claimed))
	}
	if err := repo.FinishExecution(ctx, claimed[0], nil); err != nil {
		t.Fatal(err)
	}
	next, err := repo.ClaimExecution(ctx, time.Minute)
	if err != nil || next.Token == uuid.Nil || next.DeploymentID == claimed[0].DeploymentID {
		t.Fatal(next, err)
	}
}

func TestProgressiveRequestsNeverFallBackToSimulation(t *testing.T) {
	ctx, pool := newIsolatedDeploymentTestPool(t)
	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatal(err)
	}
	repo := NewDeploymentRepository(pool)
	repo.SetExecutionMode("simulated")
	d := model.Deployment{ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging", Namespace: "test", Image: "image", GitCommitSHA: "abcdef1", Status: model.DeploymentStatusQueued, CreatedAt: time.Now(), UpdatedAt: time.Now(), Strategy: model.DeploymentStrategy{Type: "canary"}}
	if err := repo.Create(ctx, d); err != nil {
		t.Fatal(err)
	}
	lease, err := repo.ClaimExecution(ctx, time.Minute)
	if err != nil || lease.Token == uuid.Nil || !lease.ProgressiveUnsupported {
		t.Fatal(lease, err)
	}
}
