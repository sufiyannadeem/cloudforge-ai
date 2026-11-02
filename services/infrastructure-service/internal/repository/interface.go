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

	// TransitionStatus atomically changes status only when the current status is
	// one of from. It returns ErrResourceConflict if the transition loses a race.
	TransitionStatus(ctx context.Context, id uuid.UUID, from []model.ResourceStatus, to model.ResourceStatus) error

	// SavePlan persists plan metadata only while the resource is still planning.
	SavePlan(ctx context.Context, resource model.InfrastructureResource) error

	// SaveDestroyPlan persists destroy plan metadata and moves the resource from
	// planning to awaiting_destroy_approval atomically.
	SaveDestroyPlan(ctx context.Context, resource model.InfrastructureResource) error

	// UpdateEditable changes only client-editable fields and only if status has
	// not changed since the service read the resource.
	UpdateEditable(ctx context.Context, id uuid.UUID, input model.UpdateResourceInput, expectedStatus model.ResourceStatus) error

	// DeleteIfStatusAllowed deletes a resource only when its current status
	// permits deletion. It returns ErrResourceConflict if the status changed
	// or deletion is not allowed.
	DeleteIfStatusAllowed(ctx context.Context, id uuid.UUID) error
}
