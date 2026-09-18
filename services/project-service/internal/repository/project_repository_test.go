package repository

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
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
