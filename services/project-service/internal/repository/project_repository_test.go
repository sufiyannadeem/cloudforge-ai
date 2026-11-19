package repository

import (
	"context"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func setupTestRepository(t *testing.T) (*pgxpool.Pool, ProjectRepository) {
	t.Helper()

	databaseURL := os.Getenv("TEST_DATABASE_URL")

	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not set")
	}

	ctx, cancel := context.WithTimeout(
		context.Background(),
		10*time.Second,
	)
	defer cancel()

	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("create test database pool: %v", err)
	}

	t.Cleanup(func() {
		pool.Close()
	})

	if err := pool.Ping(ctx); err != nil {
		t.Fatalf("ping test database: %v", err)
	}

	repo := NewProjectRepository(pool)

	return pool, repo
}

func cleanupProjects(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	_, err := pool.Exec(ctx, "DELETE FROM projects")
	if err != nil {
		t.Fatalf("clean up projects: %v", err)
	}
}

func TestProjectRepositoryCreateAndGetByID(t *testing.T) {
	pool, repo := setupTestRepository(t)
	cleanupProjects(t, pool)

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	description := "CloudForge AI platform project"

	input := model.CreateProjectInput{
		Name:          "repository-create-test",
		Description:   &description,
		RepositoryURL: "https://github.com/example/cloudforge-test",
		DefaultBranch: "main",
	}

	createdProject, err := repo.Create(ctx, input)
	if err != nil {
		t.Fatalf("create project: %v", err)
	}

	if createdProject.ID == uuid.Nil {
		t.Fatal("expected a generated project ID")
	}

	if createdProject.Name != input.Name {
		t.Fatalf(
			"expected project name %q, got %q",
			input.Name,
			createdProject.Name,
		)
	}

	retrievedProject, err := repo.GetByID(
		ctx,
		createdProject.ID,
	)
	if err != nil {
		t.Fatalf("get project by ID: %v", err)
	}

	if retrievedProject.ID != createdProject.ID {
		t.Fatalf(
			"expected ID %s, got %s",
			createdProject.ID,
			retrievedProject.ID,
		)
	}

	if retrievedProject.RepositoryURL != input.RepositoryURL {
		t.Fatalf(
			"expected repository URL %q, got %q",
			input.RepositoryURL,
			retrievedProject.RepositoryURL,
		)
	}
}

func TestProjectRepositoryList(t *testing.T) {
	pool, repo := setupTestRepository(t)
	cleanupProjects(t, pool)

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	for i := 1; i <= 3; i++ {
		input := model.CreateProjectInput{
			Name:          "repository-list-test-" + uuid.NewString(),
			RepositoryURL: "https://github.com/example/repository-test",
			DefaultBranch: "main",
		}

		if _, err := repo.Create(ctx, input); err != nil {
			t.Fatalf("create project %d: %v", i, err)
		}
	}

	projects, err := repo.List(ctx, 10, 0)
	if err != nil {
		t.Fatalf("list projects: %v", err)
	}

	if len(projects) != 3 {
		t.Fatalf(
			"expected 3 projects, got %d",
			len(projects),
		)
	}
}

func TestProjectRepositoryUpdate(t *testing.T) {
	pool, repo := setupTestRepository(t)
	cleanupProjects(t, pool)

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	input := model.CreateProjectInput{
		Name:          "repository-update-test",
		RepositoryURL: "https://github.com/example/update-test",
		DefaultBranch: "main",
	}

	createdProject, err := repo.Create(ctx, input)
	if err != nil {
		t.Fatalf("create project: %v", err)
	}

	updatedName := "repository-updated-project"
	updatedBranch := "develop"

	updatedProject, err := repo.Update(
		ctx,
		createdProject.ID,
		model.UpdateProjectInput{
			Name:          &updatedName,
			DefaultBranch: &updatedBranch,
		},
	)
	if err != nil {
		t.Fatalf("update project: %v", err)
	}

	if updatedProject.Name != updatedName {
		t.Fatalf(
			"expected updated name %q, got %q",
			updatedName,
			updatedProject.Name,
		)
	}

	if updatedProject.DefaultBranch != updatedBranch {
		t.Fatalf(
			"expected updated branch %q, got %q",
			updatedBranch,
			updatedProject.DefaultBranch,
		)
	}
}

func TestProjectRepositoryDelete(t *testing.T) {
	pool, repo := setupTestRepository(t)
	cleanupProjects(t, pool)

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	input := model.CreateProjectInput{
		Name:          "repository-delete-test",
		RepositoryURL: "https://github.com/example/delete-test",
		DefaultBranch: "main",
	}

	createdProject, err := repo.Create(ctx, input)
	if err != nil {
		t.Fatalf("create project: %v", err)
	}

	if err := repo.Delete(ctx, createdProject.ID); err != nil {
		t.Fatalf("delete project: %v", err)
	}

	_, err = repo.GetByID(ctx, createdProject.ID)
	if err != ErrProjectNotFound {
		t.Fatalf(
			"expected ErrProjectNotFound, got %v",
			err,
		)
	}
}

func TestProjectListTracksVerifiedMembership(t *testing.T) {
	pool, repo := setupTestRepository(t)
	ctx := context.Background()
	owner, other := "test-"+uuid.NewString(), "test-"+uuid.NewString()
	claims := func(subject, role string) context.Context {
		return identity.WithClaims(httptest.NewRequest("GET", "/", nil),
			identity.Claims{Issuer: "frontend", Subject: subject, Role: role}).Context()
	}
	ownerCtx, otherCtx := claims(owner, "developer"), claims(other, "developer")
	for _, username := range []string{owner, other} {
		if _, err := pool.Exec(ctx, `INSERT INTO auth_users (username, role, password_hash, password_salt)
			VALUES ($1, 'developer', $2, $2)`, username, make([]byte, 32)); err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _, _ = pool.Exec(ctx, "DELETE FROM auth_users WHERE username = $1", username) })
	}
	create := func(ctx context.Context) *model.Project {
		t.Helper()
		project, err := repo.Create(ctx, model.CreateProjectInput{
			Name: uuid.NewString(), RepositoryURL: "https://example.invalid/repo", DefaultBranch: "main",
		})
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = repo.Delete(context.Background(), project.ID) })
		return project
	}
	project, legacy := create(ownerCtx), create(ctx)
	if project.CreatedBy == nil || *project.CreatedBy != owner || legacy.CreatedBy != nil {
		t.Fatal("project ownership did not come from the verified caller")
	}
	contains := func(ctx context.Context, id uuid.UUID, want bool) string {
		t.Helper()
		projects, err := repo.List(ctx, 100, 0)
		if err != nil {
			t.Fatal(err)
		}
		for _, project := range projects {
			if project.ID == id {
				if !want {
					t.Fatal("private project was listed")
				}
				return project.AccessLevel
			}
		}
		if want {
			t.Fatal("visible project was omitted")
		}
		return ""
	}
	if level := contains(ownerCtx, project.ID, true); level != "owner" {
		t.Fatalf("owner list grants %q", level)
	}
	contains(ownerCtx, legacy.ID, false)
	contains(otherCtx, project.ID, false)
	if _, err := pool.Exec(ctx, "INSERT INTO project_members VALUES ($1, $2, 'viewer')", project.ID, other); err != nil {
		t.Fatal(err)
	}
	if level := contains(otherCtx, project.ID, true); level != "viewer" {
		t.Fatalf("viewer list grants %q", level)
	}
	if _, err := repo.Update(otherCtx, project.ID, model.UpdateProjectInput{}); err != ErrProjectNotFound {
		t.Fatalf("viewer was allowed to update: %v", err)
	}
	if _, err := pool.Exec(ctx, "UPDATE project_members SET level = 'maintainer' WHERE project_id = $1", project.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.Update(otherCtx, project.ID, model.UpdateProjectInput{}); err != nil {
		t.Fatal(err)
	}
	if err := repo.Delete(otherCtx, project.ID); err != ErrProjectNotFound {
		t.Fatalf("maintainer was allowed to delete: %v", err)
	}
	if _, err := pool.Exec(ctx, "DELETE FROM project_members WHERE project_id = $1", project.ID); err != nil {
		t.Fatal(err)
	}
	contains(otherCtx, project.ID, false)
}
