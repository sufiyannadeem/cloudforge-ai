package repository

import (
	"context"
	"errors"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func TestReviewBindsExactPlanAndClaimsOnce(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	schema := pgx.Identifier{"approval_" + uuid.NewString()}.Sanitize()
	if _, err := testPool.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	defer func() {
		if _, err := testPool.Exec(context.Background(), "DROP SCHEMA "+schema+" CASCADE"); err != nil {
			t.Error(err)
		}
	}()
	config := testPool.Config()
	config.ConnConfig.RuntimeParams["search_path"] = schema
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, "CREATE TABLE projects (id uuid PRIMARY KEY, created_by text); CREATE TABLE project_members (project_id uuid, username text, level text)"); err != nil {
		t.Fatal(err)
	}

	t.Run("rejected reconciliation", func(t *testing.T) { testRejectedReconciliation(t, ctx, pool) })
	repo := NewResourceRepository(pool)
	resource := newTestResource()
	resource.ResourceType = "aws_ec2"
	resource.RequestedBy = "requester"
	resource.Status = model.ResourceStatusPlanning
	resource.PlanHash = "saved-sha256"
	expiry := time.Now().Add(time.Hour).UTC().Truncate(time.Microsecond)
	resource.ApprovalExpiresAt = &expiry
	if _, err := pool.Exec(ctx, "INSERT INTO projects VALUES ($1, 'requester')", resource.ProjectID); err != nil {
		t.Fatal(err)
	}
	if err := repo.Create(ctx, resource); err != nil {
		t.Fatal(err)
	}
	if err := repo.SavePlan(ctx, resource); err != nil {
		t.Fatal(err)
	}
	resource, err = repo.GetByID(ctx, resource.ID)
	if err != nil {
		t.Fatal(err)
	}
	input := model.PlanReviewInput{Operation: "apply", Action: "submit", PlanHash: resource.PlanHash, Revision: resource.UpdatedAt}
	expect := func(err, want error) {
		t.Helper()
		if !errors.Is(err, want) {
			t.Fatalf("got %v, want %v", err, want)
		}
	}

	expect(repo.ClaimReviewedPlan(ctx, resource, "apply", "operator"), ErrResourceConflict)
	wrongHash := input
	wrongHash.PlanHash = "another-plan"
	expect(repo.ReviewPlan(ctx, resource.ID, wrongHash, "requester"), ErrResourceConflict)

	expect(repo.ReviewPlan(ctx, resource.ID, input, "requester"), nil)
	expect(repo.ReviewPlan(ctx, resource.ID, input, "requester"), ErrResourceConflict)
	decision := input
	decision.Action = "approve"
	expect(repo.ReviewPlan(ctx, resource.ID, decision, "requester"), ErrReviewForbidden)
	expect(repo.ReviewPlan(ctx, resource.ID, decision, "reviewer"), nil)

	if _, err := pool.Exec(ctx, "UPDATE infrastructure_resources SET environment = 'another' WHERE id = $1", resource.ID); err != nil {
		t.Fatal(err)
	}
	expect(repo.ClaimReviewedPlan(ctx, resource, "apply", "operator"), ErrResourceConflict)
	if _, err := pool.Exec(ctx, "UPDATE infrastructure_resources SET environment = $2, approval_expires_at = clock_timestamp() WHERE id = $1", resource.ID, resource.Environment); err != nil {
		t.Fatal(err)
	}
	expect(repo.ClaimReviewedPlan(ctx, resource, "apply", "operator"), ErrResourceConflict)
	if _, err := pool.Exec(ctx, "UPDATE infrastructure_resources SET approval_expires_at = $2 WHERE id = $1", resource.ID, expiry); err != nil {
		t.Fatal(err)
	}
	stale := resource
	stale.UpdatedAt = stale.UpdatedAt.Add(-time.Microsecond)
	expect(repo.ClaimReviewedPlan(ctx, stale, "apply", "operator"), ErrResourceConflict)

	results := make(chan error, 2)
	for range 2 {
		go func() { results <- repo.ClaimReviewedPlan(ctx, resource, "apply", "operator") }()
	}
	winners := 0
	for range 2 {
		if err := <-results; err == nil {
			winners++
		} else {
			expect(err, ErrResourceConflict)
		}
	}
	if winners != 1 {
		t.Fatalf("expected one execution claim, got %d", winners)
	}
	resource.TerraformResourceID = "i-0123456789abcdef0"
	verifiedAt := time.Now().UTC().Truncate(time.Microsecond)
	resource.AWSLastVerifiedAt = &verifiedAt
	resource.EC2Attribution = &model.EC2Attribution{AccountID: "123456789012", InstanceID: "i-0123456789abcdef0"}
	expect(repo.FinishReviewedPlan(ctx, resource, "apply", model.ResourceStatusActive, true), nil)
	current, err := repo.GetByID(ctx, resource.ID)
	if err != nil || current.TerraformResourceID != resource.TerraformResourceID || current.LastExecutionError != "" || current.AWSLastVerifiedAt == nil || !current.AWSLastVerifiedAt.Equal(verifiedAt) {
		t.Fatalf("provider ID or success evidence did not persist: %v", err)
	}
	var instance string
	err = pool.QueryRow(ctx, `
		SELECT instance_id FROM infrastructure_ec2_attribution
		WHERE resource_id = $1 AND project_id = $2 AND environment = $3 AND region = $4 AND account_id = $5
	`, resource.ID, resource.ProjectID, resource.Environment, resource.Region, resource.EC2Attribution.AccountID).Scan(&instance)
	if err != nil || instance != resource.EC2Attribution.InstanceID {
		t.Fatalf("execution did not save verified attribution: %v", err)
	}
	history, err := repo.PlanReviews(ctx, resource.ID)
	if err != nil || len(history) != 1 || history[0].Status != "succeeded" ||
		history[0].DecidedBy == nil || *history[0].DecidedBy != "reviewer" || history[0].ExecutedBy == nil {
		t.Fatalf("execution history incomplete: %v", err)
	}
	access := identity.ProjectAccess{DB: pool}
	for _, tc := range []struct {
		subject, role string
		want          error
	}{
		{"requester", "developer", nil},
		{"other-project-owner", "developer", identity.ErrProjectHidden},
		{"reliability", "sre", nil},
		{"operator", "platform-engineer", nil},
	} {
		req := identity.WithClaims(httptest.NewRequest("GET", "/", nil), identity.Claims{
			Issuer: "frontend", Subject: tc.subject, Role: tc.role,
		})
		expect(access.Resource(req.Context(), "infrastructure", resource.ID.String(), false), tc.want)
	}
	for _, member := range []struct {
		subject string
		count   int
	}{{"requester", 1}, {"no-projects", 0}} {
		req := access.Attach(identity.WithClaims(httptest.NewRequest("GET", "/", nil), identity.Claims{
			Issuer: "frontend", Subject: member.subject, Role: "developer",
		}))
		items, err := repo.List(req.Context(), 100, 0)
		if err != nil || items == nil || len(items) != member.count {
			t.Fatalf("inventory for %s: %d items, %v", member.subject, len(items), err)
		}
	}
	saveDestroy := func(from model.ResourceStatus, hash string) model.InfrastructureResource {
		t.Helper()
		expect(repo.TransitionStatus(ctx, resource.ID, []model.ResourceStatus{from}, model.ResourceStatusPlanning), nil)
		resource.DestroyPlanHash = hash
		resource.DestroyRequestedBy = "requester"
		resource.ApprovalExpiresAt = &expiry
		expect(repo.SaveDestroyPlan(ctx, resource), nil)
		current, err := repo.GetByID(ctx, resource.ID)
		expect(err, nil)
		return current
	}
	destroy := saveDestroy(model.ResourceStatusActive, "original-destroy")
	review := model.PlanReviewInput{Operation: "destroy", Action: "submit", PlanHash: destroy.DestroyPlanHash, Revision: destroy.UpdatedAt}
	expect(repo.ReviewPlan(ctx, resource.ID, review, "requester"), nil)
	review.Action = "approve"
	expect(repo.ReviewPlan(ctx, resource.ID, review, "reviewer"), nil)
	for range 2 {
		go func() { results <- repo.ClaimReviewedPlan(ctx, destroy, "destroy", "operator") }()
	}
	winners = 0
	for range 2 {
		if err := <-results; err == nil {
			winners++
		} else {
			expect(err, ErrResourceConflict)
		}
	}
	if winners != 1 {
		t.Fatalf("expected one destroy claim, got %d", winners)
	}
	expect(repo.FinishReviewedPlan(ctx, destroy, "destroy", model.ResourceStatusDestroyFailed, false), nil)
	assertDestroyFailed := func() {
		t.Helper()
		current, err := repo.GetByID(ctx, resource.ID)
		expect(err, nil)
		if current.Status != model.ResourceStatusDestroyFailed {
			t.Fatalf("failed destroy became %s", current.Status)
		}
	}
	assertDestroyFailed()
	expect(repo.DeleteIfStatusAllowed(ctx, resource.ID), ErrResourceConflict)
	expect(repo.ClaimReviewedPlan(ctx, destroy, "destroy", "operator"), ErrResourceConflict)
	fresh := saveDestroy(model.ResourceStatusDestroyFailed, "reconciled-destroy")
	expect(repo.ClaimReviewedPlan(ctx, fresh, "destroy", "operator"), ErrResourceConflict)
	review = model.PlanReviewInput{Operation: "destroy", Action: "submit", PlanHash: fresh.DestroyPlanHash, Revision: fresh.UpdatedAt}
	expect(repo.ReviewPlan(ctx, resource.ID, review, "requester"), nil)
	review.Action = "reject"
	expect(repo.ReviewPlan(ctx, resource.ID, review, "reviewer"), nil)
	assertDestroyFailed()
	fresh = saveDestroy(model.ResourceStatusDestroyFailed, "second-reconciled-destroy")
	expect(repo.InvalidatePlan(ctx, fresh, "destroy", model.ResourceStatusActive), nil)
	assertDestroyFailed()
	fresh = saveDestroy(model.ResourceStatusDestroyFailed, "approved-reconciled-destroy")
	review = model.PlanReviewInput{Operation: "destroy", Action: "submit", PlanHash: fresh.DestroyPlanHash, Revision: fresh.UpdatedAt}
	expect(repo.ReviewPlan(ctx, resource.ID, review, "requester"), nil)
	review.Action = "approve"
	expect(repo.ReviewPlan(ctx, resource.ID, review, "reviewer"), nil)
	expect(repo.ClaimReviewedPlan(ctx, fresh, "destroy", "operator"), nil)
	expect(repo.FinishReviewedPlan(ctx, fresh, "destroy", model.ResourceStatusDestroyed, true), nil)
	final, err := repo.GetByID(ctx, resource.ID)
	expect(err, nil)
	if final.Status != model.ResourceStatusDestroyed {
		t.Fatalf("reconciled destroy ended in %s", final.Status)
	}
	expect(repo.DeleteIfStatusAllowed(ctx, resource.ID), nil)

	partial := newTestResource()
	partial.Status = model.ResourceStatusPlanning
	partial.ProjectID = resource.ProjectID
	partial.RequestedBy = "requester"
	partial.PlanHash = "partially-executed-apply"
	partial.ApprovalExpiresAt = &expiry
	expect(repo.Create(ctx, partial), nil)
	expect(repo.SavePlan(ctx, partial), nil)
	partial, err = repo.GetByID(ctx, partial.ID)
	expect(err, nil)
	review = model.PlanReviewInput{Operation: "apply", Action: "submit", PlanHash: partial.PlanHash, Revision: partial.UpdatedAt}
	expect(repo.ReviewPlan(ctx, partial.ID, review, "requester"), nil)
	review.Action = "approve"
	expect(repo.ReviewPlan(ctx, partial.ID, review, "reviewer"), nil)
	expect(repo.ClaimReviewedPlan(ctx, partial, "apply", "operator"), nil)
	partial.TerraformResourceID = "vpc-0123456789abcdef0"
	partial.LastExecutionError = "Apply did not complete or could not be verified. Reconciliation required."
	expect(repo.FinishReviewedPlan(ctx, partial, "apply", model.ResourceStatusFailed, false), nil)
	current, err = repo.GetByID(ctx, partial.ID)
	if err != nil || current.TerraformResourceID != partial.TerraformResourceID || current.LastExecutionError != partial.LastExecutionError {
		t.Fatalf("partial execution evidence did not persist: %v", err)
	}
	expect(repo.DeleteIfStatusAllowed(ctx, partial.ID), ErrResourceConflict)

}

func testRejectedReconciliation(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	repo := NewResourceRepository(pool)
	resource := newTestResource()
	resource.Status = model.ResourceStatusActive
	resource.RequestedBy = "requester"
	resource.PlanHash = "reconciliation-hash"
	expiry := time.Now().Add(time.Hour).UTC().Truncate(time.Microsecond)
	resource.ApprovalExpiresAt = &expiry
	if _, err := pool.Exec(ctx, "INSERT INTO projects VALUES ($1, 'requester')", resource.ProjectID); err != nil {
		t.Fatal(err)
	}
	defer pool.Exec(context.Background(), "DELETE FROM projects WHERE id=$1", resource.ProjectID)
	if err := repo.Create(ctx, resource); err != nil {
		t.Fatal(err)
	}
	if err := repo.TransitionStatus(ctx, resource.ID, []model.ResourceStatus{model.ResourceStatusActive}, model.ResourceStatusPlanning); err != nil {
		t.Fatal(err)
	}
	if err := repo.SavePlan(ctx, resource); err != nil {
		t.Fatal(err)
	}
	resource, err := repo.GetByID(ctx, resource.ID)
	if err != nil {
		t.Fatal(err)
	}
	input := model.PlanReviewInput{Operation: "apply", Action: "submit", PlanHash: resource.PlanHash, Revision: resource.UpdatedAt}
	if err := repo.ReviewPlan(ctx, resource.ID, input, "requester"); err != nil {
		t.Fatal(err)
	}
	input.Action = "reject"
	if err := repo.ReviewPlan(ctx, resource.ID, input, "operator"); err != nil {
		t.Fatal(err)
	}
	resource, err = repo.GetByID(ctx, resource.ID)
	if err != nil || resource.Status != model.ResourceStatusActive {
		t.Fatalf("rejected replan: %s, %v", resource.Status, err)
	}

	if err := repo.TransitionStatus(ctx, resource.ID, []model.ResourceStatus{model.ResourceStatusActive}, model.ResourceStatusPlanning); err != nil {
		t.Fatal(err)
	}
	if err := repo.SavePlan(ctx, resource); err != nil {
		t.Fatal(err)
	}
	resource, err = repo.GetByID(ctx, resource.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err := repo.InvalidatePlan(ctx, resource, "apply", model.ResourceStatusFailed); err != nil {
		t.Fatal(err)
	}
	resource, err = repo.GetByID(ctx, resource.ID)
	if err != nil || resource.Status != model.ResourceStatusActive {
		t.Fatalf("expired unapplied reconciliation: %s, %v", resource.Status, err)
	}
}
