package repository

import (
	"context"
	"time"

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
	TransitionStatusWithLease(ctx context.Context, id uuid.UUID, from []model.ResourceStatus, to model.ResourceStatus, ownerID string, fencingToken int64) error

	// ClaimPlan atomically transitions a resource to planning using optimistic
	// locking against resource.UpdatedAt. It returns ErrResourceConflict on race.
	ClaimPlan(ctx context.Context, resource model.InfrastructureResource) error

	// SavePlan persists plan metadata only while the resource is still planning.
	SavePlan(ctx context.Context, resource model.InfrastructureResource) error
	SavePlanWithLease(ctx context.Context, resource model.InfrastructureResource, ownerID string, fencingToken int64) error

	// SaveDestroyPlan persists destroy plan metadata and moves the resource from
	// planning to awaiting_destroy_approval atomically.
	SaveDestroyPlan(ctx context.Context, resource model.InfrastructureResource) error
	SaveDestroyPlanWithLease(ctx context.Context, resource model.InfrastructureResource, ownerID string, fencingToken int64) error

	ReviewPlan(context.Context, uuid.UUID, model.PlanReviewInput, string) error
	PlanReviews(context.Context, uuid.UUID) ([]model.PlanReview, error)
	InvalidatePlan(context.Context, model.InfrastructureResource, string, model.ResourceStatus) error
	ClaimReviewedPlan(context.Context, model.InfrastructureResource, string, string) error
	FinishReviewedPlan(context.Context, model.InfrastructureResource, string, model.ResourceStatus, bool) error
	FinishReviewedPlanWithLease(ctx context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus, succeeded bool, ownerID string, fencingToken int64) error

	// AcquireExecutionLease atomically acquires or recovers a bounded execution lease for the resource.
	// It returns ErrResourceConflict if an active unexpired lease is held by another worker.
	AcquireExecutionLease(ctx context.Context, resourceID uuid.UUID, ownerID string, operation string, ttl time.Duration) (model.ExecutionLease, error)

	// HeartbeatExecutionLease renews the lease expiration if the caller still owns the valid fencing token.
	// It returns ErrResourceConflict if the lease expired, was stolen, or lost.
	HeartbeatExecutionLease(ctx context.Context, resourceID uuid.UUID, ownerID string, fencingToken int64, ttl time.Duration) error

	// ReleaseExecutionLease releases the lease if the caller still owns the valid fencing token.
	ReleaseExecutionLease(ctx context.Context, resourceID uuid.UUID, ownerID string, fencingToken int64) error

	// GetExecutionLease returns the current execution lease if one exists.
	GetExecutionLease(ctx context.Context, resourceID uuid.UUID) (model.ExecutionLease, error)

	// UpdateEditable changes only client-editable fields and only if status has
	// not changed since the service read the resource.
	UpdateEditable(ctx context.Context, id uuid.UUID, input model.UpdateResourceInput, expectedStatus model.ResourceStatus) error

	// DeleteIfStatusAllowed deletes a resource only when its current status
	// permits deletion. It returns ErrResourceConflict if the status changed
	// or deletion is not allowed.
	DeleteIfStatusAllowed(ctx context.Context, id uuid.UUID) error
}
