package service

import (
	"context"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

type ResourceManager interface {
	Create(
		ctx context.Context,
		input model.CreateResourceInput,
	) (model.InfrastructureResource, error)

	GetByID(
		ctx context.Context,
		id uuid.UUID,
	) (model.InfrastructureResource, error)

	List(
		ctx context.Context,
		limit int,
		offset int,
	) ([]model.InfrastructureResource, error)

	Update(
		ctx context.Context,
		id uuid.UUID,
		input model.UpdateResourceInput,
	) (model.InfrastructureResource, error)

	Delete(
		ctx context.Context,
		id uuid.UUID,
	) error
}
