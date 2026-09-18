package repository

import (
	"context"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

type ResourceStore interface {
	Create(ctx context.Context, resource model.InfrastructureResource) error

	GetByID(
		ctx context.Context,
		id uuid.UUID,
	) (model.InfrastructureResource, error)

	List(
		ctx context.Context,
		limit int,
		offset int,
	) ([]model.InfrastructureResource, error)

	Update(ctx context.Context, resource model.InfrastructureResource) error

	Delete(ctx context.Context, id uuid.UUID) error
}
