package service

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"
)

const defaultApprovalTTL = 30 * time.Minute

var (
	ErrInvalidProvisioningState = errors.New(
		"resource is not in a valid provisioning state",
	)

	ErrApprovalExpired = errors.New(
		"terraform plan approval has expired",
	)

	ErrPlanHashMismatch = errors.New(
		"terraform plan hash mismatch",
	)
)

type ProvisioningService struct {
	store  repository.ResourceStore
	runner terraform.Provisioner
	clock  func() time.Time
}

func NewProvisioningService(
	store repository.ResourceStore,
	runner terraform.Provisioner,
) *ProvisioningService {
	return &ProvisioningService{
		store:  store,
		runner: runner,
		clock:  time.Now,
	}
}

func (s *ProvisioningService) Plan(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	resource, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.InfrastructureResource{}, err
	}

	if !canStartPlan(resource.Status) {
		return model.InfrastructureResource{}, fmt.Errorf(
			"%w: current status=%s",
			ErrInvalidProvisioningState,
			resource.Status,
		)
	}

	if err := s.store.TransitionStatus(ctx, id,
		[]model.ResourceStatus{model.ResourceStatusPending, model.ResourceStatusFailed},
		model.ResourceStatusPlanning); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for planning: %w", err)
	}
	resource.Status = model.ResourceStatusPlanning

	result, err := s.runner.Plan(ctx, resource)
	if err != nil {
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusPlanning}, model.ResourceStatusFailed); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("terraform plan failed: %v; persist failed status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	now := result.PlanCreatedAt
	if now.IsZero() {
		now = s.clock().UTC()
	}

	approvalExpiresAt := now.Add(defaultApprovalTTL)

	resource.TerraformDirectory = result.WorkspaceDirectory
	resource.PlanPath = result.PlanPath
	resource.PlanHash = result.PlanHash
	resource.PlanSummary = result.PlanSummary
	resource.PlanCreatedAt = &now
	resource.ApprovalExpiresAt = &approvalExpiresAt
	resource.Status = model.ResourceStatusAwaitingApproval

	if err := s.store.SavePlan(ctx, resource); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("persist terraform plan metadata: %w", err)
	}

	return resource, nil
}

func (s *ProvisioningService) Apply(
	ctx context.Context,
	id uuid.UUID,
	approvedPlanHash string,
) (model.InfrastructureResource, error) {
	resource, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.InfrastructureResource{}, err
	}

	if resource.Status != model.ResourceStatusAwaitingApproval {
		return model.InfrastructureResource{}, fmt.Errorf(
			"%w: current status=%s",
			ErrInvalidProvisioningState,
			resource.Status,
		)
	}

	now := s.clock().UTC()

	if resource.ApprovalExpiresAt == nil ||
		!now.Before(*resource.ApprovalExpiresAt) {
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusAwaitingApproval}, model.ResourceStatusFailed); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("%w; persist failed status: %v", ErrApprovalExpired, updateErr)
		}

		return model.InfrastructureResource{}, ErrApprovalExpired
	}

	if approvedPlanHash == "" ||
		!equalHash(approvedPlanHash, resource.PlanHash) {
		return model.InfrastructureResource{}, ErrPlanHashMismatch
	}

	actualHash, err := hashFile(resource.PlanPath)
	if err != nil {
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusAwaitingApproval}, model.ResourceStatusFailed); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("verify terraform plan: %v; persist failed status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	if !equalHash(actualHash, resource.PlanHash) {
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusAwaitingApproval}, model.ResourceStatusFailed); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("%w; persist failed status: %v", ErrPlanHashMismatch, updateErr)
		}

		return model.InfrastructureResource{}, ErrPlanHashMismatch
	}

	if err := s.store.TransitionStatus(ctx, id,
		[]model.ResourceStatus{model.ResourceStatusAwaitingApproval}, model.ResourceStatusProvisioning); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for apply: %w", err)
	}
	resource.Status = model.ResourceStatusProvisioning

	if err := s.runner.Apply(ctx, resource); err != nil {
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusProvisioning}, model.ResourceStatusFailed); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("terraform apply failed: %v; persist failed status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	if err := s.store.TransitionStatus(ctx, id,
		[]model.ResourceStatus{model.ResourceStatusProvisioning}, model.ResourceStatusActive); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("persist active status: %w", err)
	}
	resource.Status = model.ResourceStatusActive

	return resource, nil
}

// PlanDestroy creates a destroy plan for an active resource. It never touches
// AWS; the resource then waits in awaiting_destroy_approval for a human.
// Re-planning from awaiting_destroy_approval is allowed so an expired or stale
// plan can be refreshed.
func (s *ProvisioningService) PlanDestroy(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	resource, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.InfrastructureResource{}, err
	}

	if resource.Status != model.ResourceStatusActive &&
		resource.Status != model.ResourceStatusAwaitingDestroyApproval {
		return model.InfrastructureResource{}, fmt.Errorf(
			"%w: current status=%s",
			ErrInvalidProvisioningState,
			resource.Status,
		)
	}

	// Claim the resource so concurrent destroy plans cannot race.
	if err := s.store.TransitionStatus(ctx, id,
		[]model.ResourceStatus{model.ResourceStatusActive, model.ResourceStatusAwaitingDestroyApproval},
		model.ResourceStatusPlanning); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for destroy planning: %w", err)
	}
	resource.Status = model.ResourceStatusPlanning

	result, err := s.runner.PlanDestroy(ctx, resource)
	if err != nil {
		// The infrastructure still exists, so a failed plan returns to active.
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusPlanning}, model.ResourceStatusActive); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("terraform destroy plan failed: %v; restore active status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	now := result.PlanCreatedAt
	if now.IsZero() {
		now = s.clock().UTC()
	}

	approvalExpiresAt := now.Add(defaultApprovalTTL)

	resource.DestroyPlanPath = result.PlanPath
	resource.DestroyPlanHash = result.PlanHash
	resource.ApprovalExpiresAt = &approvalExpiresAt
	resource.Status = model.ResourceStatusAwaitingDestroyApproval

	if err := s.store.SaveDestroyPlan(ctx, resource); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("persist terraform destroy plan metadata: %w", err)
	}

	return resource, nil
}

// ApplyDestroy runs the approved destroy plan. It requires an unexpired
// approval window and a caller-supplied hash matching the stored plan hash and
// the plan file on disk. Any failure returns the resource to active (it may be
// partially destroyed; a fresh destroy plan reflects the real state).
func (s *ProvisioningService) ApplyDestroy(
	ctx context.Context,
	id uuid.UUID,
	approvedPlanHash string,
) (model.InfrastructureResource, error) {
	resource, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.InfrastructureResource{}, err
	}

	if resource.Status != model.ResourceStatusAwaitingDestroyApproval {
		return model.InfrastructureResource{}, fmt.Errorf(
			"%w: current status=%s",
			ErrInvalidProvisioningState,
			resource.Status,
		)
	}

	revert := func(cause error) (model.InfrastructureResource, error) {
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusAwaitingDestroyApproval}, model.ResourceStatusActive); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("%w; restore active status: %v", cause, updateErr)
		}

		return model.InfrastructureResource{}, cause
	}

	now := s.clock().UTC()

	if resource.ApprovalExpiresAt == nil ||
		!now.Before(*resource.ApprovalExpiresAt) {
		return revert(ErrApprovalExpired)
	}

	if approvedPlanHash == "" ||
		!equalHash(approvedPlanHash, resource.DestroyPlanHash) {
		return model.InfrastructureResource{}, ErrPlanHashMismatch
	}

	actualHash, err := hashFile(resource.DestroyPlanPath)
	if err != nil {
		return revert(err)
	}

	if !equalHash(actualHash, resource.DestroyPlanHash) {
		return revert(ErrPlanHashMismatch)
	}

	if err := s.store.TransitionStatus(ctx, id,
		[]model.ResourceStatus{model.ResourceStatusAwaitingDestroyApproval}, model.ResourceStatusDestroying); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for destroy: %w", err)
	}
	resource.Status = model.ResourceStatusDestroying

	if err := s.runner.ApplyDestroy(ctx, resource); err != nil {
		if updateErr := s.store.TransitionStatus(ctx, id,
			[]model.ResourceStatus{model.ResourceStatusDestroying}, model.ResourceStatusActive); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("terraform destroy failed: %v; restore active status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	if err := s.store.TransitionStatus(ctx, id,
		[]model.ResourceStatus{model.ResourceStatusDestroying}, model.ResourceStatusDestroyed); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("persist destroyed status: %w", err)
	}
	resource.Status = model.ResourceStatusDestroyed

	return resource, nil
}

// GetPlan returns detailed plan metadata and summary for a planned resource.
func (s *ProvisioningService) GetPlan(
	ctx context.Context,
	id uuid.UUID,
) (model.PlanDetails, error) {
	resource, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.PlanDetails{}, err
	}

	if resource.PlanHash == "" && resource.DestroyPlanHash == "" {
		return model.PlanDetails{}, errors.New("no plan exists for resource")
	}

	now := s.clock().UTC()
	isExpired := false
	if resource.ApprovalExpiresAt != nil {
		isExpired = !now.Before(*resource.ApprovalExpiresAt)
	}

	planHash := resource.PlanHash
	summary := resource.PlanSummary
	if resource.Status == model.ResourceStatusAwaitingDestroyApproval {
		planHash = resource.DestroyPlanHash
		if resource.DestroyPlanPath != "" {
			if data, err := os.ReadFile(resource.DestroyPlanPath + ".summary"); err == nil && len(data) > 0 {
				summary = string(data)
			}
		}
		if summary == "" {
			summary = fmt.Sprintf("Terraform destroy plan: 1 to destroy (%s: %s)", resource.ResourceType, resource.Name)
		}
	} else {
		if summary == "" && resource.PlanPath != "" {
			if data, err := os.ReadFile(resource.PlanPath + ".summary"); err == nil && len(data) > 0 {
				summary = string(data)
			}
		}
		if summary == "" {
			summary = fmt.Sprintf("Terraform plan: 1 to add, 0 to change, 0 to destroy (%s: %s)", resource.ResourceType, resource.Name)
		}
	}

	return model.PlanDetails{
		ResourceID:        resource.ID,
		ResourceName:      resource.Name,
		ResourceType:      resource.ResourceType,
		Provider:          resource.Provider,
		Region:            resource.Region,
		Environment:       resource.Environment,
		Status:            resource.Status,
		PlanHash:          planHash,
		PlanCreatedAt:     resource.PlanCreatedAt,
		ApprovalExpiresAt: resource.ApprovalExpiresAt,
		IsExpired:         isExpired,
		PlanSummary:       summary,
		Configuration:     resource.Configuration,
	}, nil
}

func canStartPlan(status model.ResourceStatus) bool {
	switch status {
	case model.ResourceStatusPending,
		model.ResourceStatusFailed:
		return true
	default:
		return false
	}
}

func equalHash(a, b string) bool {
	if len(a) != len(b) {
		return false
	}

	var diff byte

	for i := range a {
		diff |= a[i] ^ b[i]
	}

	return diff == 0
}

func hashFile(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf("open terraform plan: %w", err)
	}
	defer file.Close()

	hash := sha256.New()

	if _, err := file.WriteTo(hash); err != nil {
		return "", fmt.Errorf("hash terraform plan: %w", err)
	}

	return fmt.Sprintf("%x", hash.Sum(nil)), nil
}
