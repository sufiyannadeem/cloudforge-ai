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

	resource.Status = model.ResourceStatusPlanning

	if err := s.store.Update(ctx, resource); err != nil {
		return model.InfrastructureResource{}, err
	}

	result, err := s.runner.Plan(ctx, resource)
	if err != nil {
		resource.Status = model.ResourceStatusFailed

		if updateErr := s.store.Update(ctx, resource); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf(
				"terraform plan failed: %v; persist failed status: %w",
				err,
				updateErr,
			)
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
	resource.PlanCreatedAt = &now
	resource.ApprovalExpiresAt = &approvalExpiresAt
	resource.Status = model.ResourceStatusAwaitingApproval

	if err := s.store.Update(ctx, resource); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf(
			"persist terraform plan metadata: %w",
			err,
		)
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
		resource.Status = model.ResourceStatusFailed

		if updateErr := s.store.Update(ctx, resource); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf(
				"%w; persist failed status: %v",
				ErrApprovalExpired,
				updateErr,
			)
		}

		return model.InfrastructureResource{}, ErrApprovalExpired
	}

	if approvedPlanHash == "" ||
		!equalHash(approvedPlanHash, resource.PlanHash) {
		return model.InfrastructureResource{}, ErrPlanHashMismatch
	}

	actualHash, err := hashFile(resource.PlanPath)
	if err != nil {
		resource.Status = model.ResourceStatusFailed

		if updateErr := s.store.Update(ctx, resource); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf(
				"verify terraform plan: %v; persist failed status: %w",
				err,
				updateErr,
			)
		}

		return model.InfrastructureResource{}, err
	}

	if !equalHash(actualHash, resource.PlanHash) {
		resource.Status = model.ResourceStatusFailed

		if updateErr := s.store.Update(ctx, resource); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf(
				"%w; persist failed status: %v",
				ErrPlanHashMismatch,
				updateErr,
			)
		}

		return model.InfrastructureResource{}, ErrPlanHashMismatch
	}

	resource.Status = model.ResourceStatusProvisioning

	if err := s.store.Update(ctx, resource); err != nil {
		return model.InfrastructureResource{}, err
	}

	if err := s.runner.Apply(ctx, resource); err != nil {
		resource.Status = model.ResourceStatusFailed

		if updateErr := s.store.Update(ctx, resource); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf(
				"terraform apply failed: %v; persist failed status: %w",
				err,
				updateErr,
			)
		}

		return model.InfrastructureResource{}, err
	}

	resource.Status = model.ResourceStatusActive

	if err := s.store.Update(ctx, resource); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf(
			"persist active status: %w",
			err,
		)
	}

	return resource, nil
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
