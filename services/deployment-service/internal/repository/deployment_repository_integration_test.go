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
		deployment.Status = model.DeploymentStatusQueued
		deployment.UpdatedAt = time.Now().UTC()

		err := repo.Update(ctx, deployment)
		if err != nil {
			t.Fatalf("Update() failed: %v", err)
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
