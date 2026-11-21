//go:build integration

package repository

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

func TestDeploymentRepositoryCRUD(t *testing.T) {
	databaseURL := os.Getenv("DATABASE_URL")

	if databaseURL == "" {
		t.Fatal("DATABASE_URL is required for integration tests")
	}

	ctx, cancel := context.WithTimeout(
		context.Background(),
		10*time.Second,
	)
	defer cancel()

	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("failed to create database pool: %v", err)
	}
	defer pool.Close()

	if err := pool.Ping(ctx); err != nil {
		t.Fatalf("failed to connect to database: %v", err)
	}

	repo := NewDeploymentRepository(pool)

	projectID := uuid.New()
	deploymentID := uuid.New()

	deployment := model.Deployment{
		ID:           deploymentID,
		ProjectID:    projectID,
		Environment:  "development",
		Image:        "nginx:1.27-alpine",
		GitCommitSHA: "abcdef1234567",
		Namespace:    "integration-test",
		Status:       model.DeploymentStatusPending,
		CreatedAt:    time.Now().UTC(),
		UpdatedAt:    time.Now().UTC(),
	}

	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(
			context.Background(),
			5*time.Second,
		)
		defer cleanupCancel()

		_ = repo.Delete(cleanupCtx, deploymentID)
	})

	t.Run("Create", func(t *testing.T) {
		err := repo.Create(ctx, deployment)
		if err != nil {
			t.Fatalf("Create() failed: %v", err)
		}
	})

	t.Run("GetByID", func(t *testing.T) {
		result, err := repo.GetByID(ctx, deploymentID)
		if err != nil {
			t.Fatalf("GetByID() failed: %v", err)
		}

		if result.ID != deploymentID {
			t.Fatalf("expected ID %s, got %s", deploymentID, result.ID)
		}

		if result.Status != model.DeploymentStatusPending {
			t.Fatalf(
				"expected status %s, got %s",
				model.DeploymentStatusPending,
				result.Status,
			)
		}
	})

	t.Run("List", func(t *testing.T) {
		results, err := repo.List(ctx, 20, 0)
		if err != nil {
			t.Fatalf("List() failed: %v", err)
		}

		found := false

		for _, item := range results {
			if item.ID == deploymentID {
				found = true
				break
			}
		}

		if !found {
			t.Fatalf("created deployment %s was not found in list", deploymentID)
		}
	})

	t.Run("Update", func(t *testing.T) {
		expected, err := repo.GetByID(ctx, deploymentID)
		if err != nil {
			t.Fatal(err)
		}
		deployment.Status = model.DeploymentStatusQueued
		deployment.UpdatedAt = time.Now().UTC()

		errors := concurrentWrites(2, func() error {
			return repo.Update(ctx, deployment, expected)
		})
		switch {
		case errors[0] == nil && errors[1] == ErrDeploymentConflict:
		case errors[1] == nil && errors[0] == ErrDeploymentConflict:
		default:
			t.Fatalf("expected one transition and one conflict, got %v", errors)
		}

		result, err := repo.GetByID(ctx, deploymentID)
		if err != nil {
			t.Fatalf("GetByID() after update failed: %v", err)
		}

		if result.Status != model.DeploymentStatusQueued {
			t.Fatalf(
				"expected status %s, got %s",
				model.DeploymentStatusQueued,
				result.Status,
			)
		}
	})

	t.Run("Stale configuration update", func(t *testing.T) {
		expected, err := repo.GetByID(ctx, deploymentID)
		if err != nil {
			t.Fatal(err)
		}
		imageUpdate := expected
		imageUpdate.Image = "nginx:stable"
		if err := repo.Update(ctx, imageUpdate, expected); err != nil {
			t.Fatal(err)
		}
		namespaceUpdate := expected
		namespaceUpdate.Namespace = "stale-namespace"
		if err := repo.Update(ctx, namespaceUpdate, expected); err != ErrDeploymentConflict {
			t.Fatalf("expected stale update conflict, got %v", err)
		}
		current, err := repo.GetByID(ctx, deploymentID)
		if err != nil {
			t.Fatal(err)
		}
		if current.Image != imageUpdate.Image || current.Namespace != expected.Namespace {
			t.Fatal("stale write changed deployment configuration")
		}
	})

	t.Run("Concurrent attempt allocation", func(t *testing.T) {
		attempts, err := NewDeploymentAttemptRepository(pool)
		if err != nil {
			t.Fatal(err)
		}
		const count = 8
		for _, err := range concurrentWrites(count, func() error {
			now := time.Now()
			return attempts.Create(ctx, model.DeploymentAttempt{
				ID: uuid.New(), DeploymentID: deploymentID, Status: model.AttemptStatusRunning,
				StartedAt: now, CreatedAt: now,
			})
		}) {
			if err != nil {
				t.Fatal(err)
			}
		}
		history, err := attempts.ListByDeploymentID(ctx, deploymentID, count, 0)
		if err != nil {
			t.Fatal(err)
		}
		numbers := make(map[int]bool, count)
		for _, attempt := range history {
			numbers[attempt.AttemptNumber] = true
		}
		for number := 1; number <= count; number++ {
			if !numbers[number] {
				t.Fatalf("attempt number %d missing from %v", number, numbers)
			}
		}
	})

	t.Run("Delete", func(t *testing.T) {
		err := repo.Delete(ctx, deploymentID)
		if err != nil {
			t.Fatalf("Delete() failed: %v", err)
		}

		_, err = repo.GetByID(ctx, deploymentID)
		if err != ErrDeploymentNotFound {
			t.Fatalf(
				"expected ErrDeploymentNotFound, got %v",
				err,
			)
		}
	})
}

func concurrentWrites(count int, write func() error) []error {
	start := make(chan struct{})
	results := make(chan error, count)
	for range count {
		go func() {
			<-start
			results <- write()
		}()
	}
	close(start)
	errs := make([]error, count)
	for i := range errs {
		errs[i] = <-results
	}
	return errs
}
