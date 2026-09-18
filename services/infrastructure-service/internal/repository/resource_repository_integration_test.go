package repository

import (
	"context"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/migration"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

var testPool *pgxpool.Pool

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(
		context.Background(),
		10*time.Second,
	)
	defer cancel()

	databaseURL := os.Getenv("TEST_DATABASE_URL")

	if databaseURL == "" {
		databaseURL = "postgres://cloudforge:cloudforge_password@localhost:5432/cloudforge?sslmode=disable"
	}

	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create test database pool: %v\n", err)
		os.Exit(1)
	}

	if err := pool.Ping(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "failed to connect to test database: %v\n", err)
		pool.Close()
		os.Exit(1)
	}

	if err := migration.NewRunner(pool).Run(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "failed to run migrations: %v\n", err)
		pool.Close()
		os.Exit(1)
	}

	testPool = pool

	exitCode := m.Run()

	pool.Close()

	os.Exit(exitCode)
}

func newTestRepository() *ResourceRepository {
	return NewResourceRepository(testPool)
}

func newTestResource() model.InfrastructureResource {
	now := time.Now().UTC()

	return model.InfrastructureResource{
		ID:                 uuid.New(),
		Name:               "Test VPC",
		Description:        "Repository integration test resource",
		Provider:           model.ProviderAWS,
		Region:             "eu-west-1",
		Environment:        "testing",
		Status:             model.ResourceStatusActive,
		TerraformDirectory: "terraform/test/vpc",
		CreatedAt:          now,
		UpdatedAt:          now,
	}
}

func cleanupTestResource(t *testing.T, id uuid.UUID) {
	t.Helper()

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	_, err := testPool.Exec(
		ctx,
		"DELETE FROM infrastructure_resources WHERE id = $1",
		id,
	)

	if err != nil {
		t.Fatalf("failed to clean up test resource: %v", err)
	}
}

func TestResourceRepositoryCreateAndGetByID(t *testing.T) {
	repository := newTestRepository()
	resource := newTestResource()

	t.Cleanup(func() {
		cleanupTestResource(t, resource.ID)
	})

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	if err := repository.Create(ctx, resource); err != nil {
		t.Fatalf("failed to create resource: %v", err)
	}

	createdResource, err := repository.GetByID(ctx, resource.ID)
	if err != nil {
		t.Fatalf("failed to get resource: %v", err)
	}

	if createdResource.ID != resource.ID {
		t.Fatalf(
			"expected ID %s, got %s",
			resource.ID,
			createdResource.ID,
		)
	}

	if createdResource.Name != resource.Name {
		t.Fatalf(
			"expected name %q, got %q",
			resource.Name,
			createdResource.Name,
		)
	}

	if createdResource.Provider != resource.Provider {
		t.Fatalf(
			"expected provider %q, got %q",
			resource.Provider,
			createdResource.Provider,
		)
	}

	if createdResource.Region != resource.Region {
		t.Fatalf(
			"expected region %q, got %q",
			resource.Region,
			createdResource.Region,
		)
	}
}

func TestResourceRepositoryGetByIDNotFound(t *testing.T) {
	repository := newTestRepository()

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	_, err := repository.GetByID(ctx, uuid.New())

	if !errors.Is(err, ErrResourceNotFound) {
		t.Fatalf(
			"expected ErrResourceNotFound, got %v",
			err,
		)
	}
}

func TestResourceRepositoryList(t *testing.T) {
	repository := newTestRepository()

	firstResource := newTestResource()
	firstResource.Name = "List Test VPC One"

	secondResource := newTestResource()
	secondResource.Name = "List Test VPC Two"

	t.Cleanup(func() {
		cleanupTestResource(t, firstResource.ID)
		cleanupTestResource(t, secondResource.ID)
	})

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	if err := repository.Create(ctx, firstResource); err != nil {
		t.Fatalf("failed to create first resource: %v", err)
	}

	if err := repository.Create(ctx, secondResource); err != nil {
		t.Fatalf("failed to create second resource: %v", err)
	}

	resources, err := repository.List(ctx, 10, 0)
	if err != nil {
		t.Fatalf("failed to list resources: %v", err)
	}

	foundFirst := false
	foundSecond := false

	for _, resource := range resources {
		if resource.ID == firstResource.ID {
			foundFirst = true
		}

		if resource.ID == secondResource.ID {
			foundSecond = true
		}
	}

	if !foundFirst {
		t.Fatal("first test resource was not found in list")
	}

	if !foundSecond {
		t.Fatal("second test resource was not found in list")
	}
}

func TestResourceRepositoryListPagination(t *testing.T) {
	repository := newTestRepository()

	resources, err := repository.List(
		context.Background(),
		1,
		0,
	)
	if err != nil {
		t.Fatalf("failed to list resources with pagination: %v", err)
	}

	if len(resources) > 1 {
		t.Fatalf(
			"expected at most 1 resource, got %d",
			len(resources),
		)
	}
}

func TestResourceRepositoryUpdate(t *testing.T) {
	repository := newTestRepository()
	resource := newTestResource()

	t.Cleanup(func() {
		cleanupTestResource(t, resource.ID)
	})

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	if err := repository.Create(ctx, resource); err != nil {
		t.Fatalf("failed to create resource: %v", err)
	}

	resource.Name = "Updated Test VPC"
	resource.Description = "Updated description"
	resource.Environment = "staging"
	resource.Status = model.ResourceStatusInactive
	resource.UpdatedAt = time.Now().UTC()

	if err := repository.Update(ctx, resource); err != nil {
		t.Fatalf("failed to update resource: %v", err)
	}

	updatedResource, err := repository.GetByID(ctx, resource.ID)
	if err != nil {
		t.Fatalf("failed to retrieve updated resource: %v", err)
	}

	if updatedResource.Name != "Updated Test VPC" {
		t.Fatalf(
			"expected updated name, got %q",
			updatedResource.Name,
		)
	}

	if updatedResource.Description != "Updated description" {
		t.Fatalf(
			"expected updated description, got %q",
			updatedResource.Description,
		)
	}

	if updatedResource.Environment != "staging" {
		t.Fatalf(
			"expected environment staging, got %q",
			updatedResource.Environment,
		)
	}

	if updatedResource.Status != model.ResourceStatusInactive {
		t.Fatalf(
			"expected inactive status, got %q",
			updatedResource.Status,
		)
	}
}

func TestResourceRepositoryUpdateNotFound(t *testing.T) {
	repository := newTestRepository()
	resource := newTestResource()

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	err := repository.Update(ctx, resource)

	if !errors.Is(err, ErrResourceNotFound) {
		t.Fatalf(
			"expected ErrResourceNotFound, got %v",
			err,
		)
	}
}

func TestResourceRepositoryDelete(t *testing.T) {
	repository := newTestRepository()
	resource := newTestResource()

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	if err := repository.Create(ctx, resource); err != nil {
		t.Fatalf("failed to create resource: %v", err)
	}

	if err := repository.Delete(ctx, resource.ID); err != nil {
		t.Fatalf("failed to delete resource: %v", err)
	}

	_, err := repository.GetByID(ctx, resource.ID)

	if !errors.Is(err, ErrResourceNotFound) {
		t.Fatalf(
			"expected ErrResourceNotFound after deletion, got %v",
			err,
		)
	}
}

func TestResourceRepositoryDeleteNotFound(t *testing.T) {
	repository := newTestRepository()

	ctx, cancel := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancel()

	err := repository.Delete(ctx, uuid.New())

	if !errors.Is(err, ErrResourceNotFound) {
		t.Fatalf(
			"expected ErrResourceNotFound, got %v",
			err,
		)
	}
}
