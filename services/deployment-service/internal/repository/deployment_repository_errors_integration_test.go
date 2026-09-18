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

func TestDeploymentRepositoryNotFoundErrors(t *testing.T) {
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

	nonExistentID := uuid.New()

	t.Run("GetByID returns not found", func(t *testing.T) {
		_, err := repo.GetByID(ctx, nonExistentID)

		if err != ErrDeploymentNotFound {
			t.Fatalf(
				"expected ErrDeploymentNotFound, got %v",
				err,
			)
		}
	})

	t.Run("Update returns not found", func(t *testing.T) {
		deployment := model.Deployment{
			ID:           nonExistentID,
			ProjectID:    uuid.New(),
			Environment:  "development",
			Image:        "nginx:1.27-alpine",
			GitCommitSHA: "abcdef1234567",
			Namespace:    "test-namespace",
			Status:       model.DeploymentStatusPending,
			CreatedAt:    time.Now().UTC(),
			UpdatedAt:    time.Now().UTC(),
		}

		err := repo.Update(ctx, deployment)

		if err != ErrDeploymentNotFound {
			t.Fatalf(
				"expected ErrDeploymentNotFound, got %v",
				err,
			)
		}
	})

	t.Run("Delete returns not found", func(t *testing.T) {
		err := repo.Delete(ctx, nonExistentID)

		if err != ErrDeploymentNotFound {
			t.Fatalf(
				"expected ErrDeploymentNotFound, got %v",
				err,
			)
		}
	})
}
