package service

import (
	"context"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type DeploymentManager interface {
	Create(
		ctx context.Context,
		input model.CreateDeploymentInput,
	) (model.Deployment, error)

	GetByID(
		ctx context.Context,
		id uuid.UUID,
	) (model.Deployment, error)

	List(
		ctx context.Context,
		limit int,
		offset int,
	) ([]model.Deployment, error)

	Update(
		ctx context.Context,
		id uuid.UUID,
		input model.UpdateDeploymentInput,
	) (model.Deployment, error)

	Delete(
		ctx context.Context,
		id uuid.UUID,
	) error
}

type DeploymentQueueManager interface {
	QueuePendingDeployment(
		ctx context.Context,
		id uuid.UUID,
	) error

	ReleaseQueuedDeployment(
		ctx context.Context,
		id uuid.UUID,
	) error
}

type deploymentQueueStore interface {
	ClaimPendingDeployment(
		ctx context.Context,
		id uuid.UUID,
		updatedAt time.Time,
	) error

	ReleaseQueuedDeployment(
		ctx context.Context,
		id uuid.UUID,
		updatedAt time.Time,
	) error
}
