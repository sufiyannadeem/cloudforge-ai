package repository

import (
	"context"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type DeploymentStore interface {
	Create(ctx context.Context, deployment model.Deployment) error

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
		deployment model.Deployment,
	) error

	Delete(
		ctx context.Context,
		id uuid.UUID,
	) error
}
