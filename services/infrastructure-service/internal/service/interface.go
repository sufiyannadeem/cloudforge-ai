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

type ProvisioningManager interface {
	Plan(
		ctx context.Context,
		id uuid.UUID,
	) (model.InfrastructureResource, error)

	Apply(
		ctx context.Context,
		id uuid.UUID,
		planHash string,
	) (model.InfrastructureResource, error)

	// PlanDestroy creates a hashed destroy plan for an active resource.
	PlanDestroy(
		ctx context.Context,
		id uuid.UUID,
	) (model.InfrastructureResource, error)

	// ApplyDestroy applies the destroy plan only if planHash matches the
	// stored, unexpired plan.
	ApplyDestroy(
		ctx context.Context,
		id uuid.UUID,
		planHash string,
	) (model.InfrastructureResource, error)

	// GetPlan returns the plan summary and details for a planned resource.
	GetPlan(
		ctx context.Context,
		id uuid.UUID,
	) (model.PlanDetails, error)
}
