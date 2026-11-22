package service

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

var ErrReviewDenied = errors.New("plan review permission denied")

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

type ExecutionLocker struct {
	mu     sync.Mutex
	active map[uuid.UUID]string
}

func NewExecutionLocker() *ExecutionLocker {
	return &ExecutionLocker{
		active: make(map[uuid.UUID]string),
	}
}

func (l *ExecutionLocker) TryLock(id uuid.UUID, op string) (func(), bool) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if _, exists := l.active[id]; exists {
		return nil, false
	}
	l.active[id] = op
	return func() {
		l.mu.Lock()
		delete(l.active, id)
		l.mu.Unlock()
	}, true
}

const (
	defaultLeaseTTL          = 30 * time.Second
	defaultHeartbeatInterval = 5 * time.Second
)

type ProvisioningService struct {
	store             repository.ResourceStore
	runner            terraform.Provisioner
	clock             func() time.Time
	locker            *ExecutionLocker
	replicaID         string
	leaseTTL          time.Duration
	heartbeatInterval time.Duration
}

func NewProvisioningService(
	store repository.ResourceStore,
	runner terraform.Provisioner,
) *ProvisioningService {
	replicaID, err := os.Hostname()
	if err != nil || replicaID == "" {
		replicaID = uuid.NewString()
	}
	return &ProvisioningService{
		store:             store,
		runner:            runner,
		clock:             time.Now,
		locker:            NewExecutionLocker(),
		replicaID:         replicaID,
		leaseTTL:          defaultLeaseTTL,
		heartbeatInterval: defaultHeartbeatInterval,
	}
}

func (s *ProvisioningService) tryLock(id uuid.UUID, op string) (func(), bool) {
	if s.locker == nil {
		return func() {}, true
	}
	return s.locker.TryLock(id, op)
}

// acquireExecutionOwnership acquires an in-process lock and a distributed
// PostgreSQL execution lease for (id, op). It returns:
//   - execCtx: cancelled automatically if the heartbeat lease is lost
//   - cleanup: releases the lease and local lock (idempotent via sync.Once)
//   - ownerID / fencingToken: passed to lease-validated write methods so stale
//     workers cannot overwrite state after losing ownership
func (s *ProvisioningService) acquireExecutionOwnership(
	ctx context.Context,
	id uuid.UUID,
	op string,
) (execCtx context.Context, cleanup func(), ownerID string, fencingToken int64, err error) {
	unlockLocal, ok := s.tryLock(id, op)
	if !ok {
		return nil, nil, "", 0, fmt.Errorf("%w: operation already active on resource %s", repository.ErrResourceConflict, id)
	}

	if s.store == nil {
		return ctx, unlockLocal, "", 0, nil
	}

	ttl := s.leaseTTL
	if ttl <= 0 {
		ttl = defaultLeaseTTL
	}
	hbInterval := s.heartbeatInterval
	if hbInterval <= 0 {
		hbInterval = defaultHeartbeatInterval
	}

	ownerID = fmt.Sprintf("%s:%s", s.replicaID, uuid.NewString())
	lease, leaseErr := s.store.AcquireExecutionLease(ctx, id, ownerID, op, ttl)
	if leaseErr != nil {
		unlockLocal()
		return nil, nil, "", 0, fmt.Errorf("%w: acquire distributed execution lease: %v", repository.ErrResourceConflict, leaseErr)
	}
	fencingToken = lease.FencingToken

	var cancelExec context.CancelFunc
	execCtx, cancelExec = context.WithCancel(ctx)
	stopHeartbeat := make(chan struct{})
	var heartbeatWg sync.WaitGroup
	heartbeatWg.Add(1)

	go func() {
		defer heartbeatWg.Done()
		ticker := time.NewTicker(hbInterval)
		defer ticker.Stop()

		for {
			select {
			case <-stopHeartbeat:
				return
			case <-execCtx.Done():
				return
			case <-ticker.C:
				hbCtx, hbCancel := context.WithTimeout(context.Background(), 3*time.Second)
				hbErr := s.store.HeartbeatExecutionLease(hbCtx, id, ownerID, fencingToken, ttl)
				hbCancel()
				if hbErr != nil {
					cancelExec()
					return
				}
			}
		}
	}()

	var once sync.Once
	cleanup = func() {
		once.Do(func() {
			close(stopHeartbeat)
			heartbeatWg.Wait()
			cancelExec()

			relCtx, relCancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
			defer relCancel()
			_ = s.store.ReleaseExecutionLease(relCtx, id, ownerID, fencingToken)
			unlockLocal()
		})
	}

	return execCtx, cleanup, ownerID, fencingToken, nil
}

func (s *ProvisioningService) Plan(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	execCtx, releaseOwnership, ownerID, fencingToken, err := s.acquireExecutionOwnership(ctx, id, "plan")
	if err != nil {
		return model.InfrastructureResource{}, err
	}
	defer releaseOwnership()

	resource, err := s.store.GetByID(execCtx, id)
	if err != nil {
		return model.InfrastructureResource{}, err
	}

	expired := resource.Status == model.ResourceStatusAwaitingApproval &&
		resource.ApprovalExpiresAt != nil && !resource.ApprovalExpiresAt.After(s.clock())
	caller := identity.FromContext(execCtx)
	reconciliation := resource.Status == model.ResourceStatusActive && caller.Human() && caller.Role == "platform-engineer"
	if !canStartPlan(resource.Status) && !expired && !reconciliation {
		return model.InfrastructureResource{}, fmt.Errorf(
			"%w: current status=%s",
			ErrInvalidProvisioningState,
			resource.Status,
		)
	}

	if expired {
		err = s.store.InvalidatePlan(execCtx, resource, "apply", model.ResourceStatusPlanning)
	} else {
		err = s.store.ClaimPlan(execCtx, resource)
	}
	if err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for planning: %w", err)
	}
	resource, err = s.store.GetByID(execCtx, id)
	if err != nil {
		_ = s.store.TransitionStatusWithLease(execCtx, id, []model.ResourceStatus{model.ResourceStatusPlanning}, model.ResourceStatusFailed, ownerID, fencingToken)
		return model.InfrastructureResource{}, err
	}
	resource.Status = model.ResourceStatusPlanning

	result, err := s.runner.Plan(execCtx, resource)
	if err != nil {
		next := model.ResourceStatusFailed
		if reconciliation {
			next = model.ResourceStatusActive
		}
		cleanupCtx, cleanupCancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
		updateErr := s.store.TransitionStatusWithLease(cleanupCtx, id,
			[]model.ResourceStatus{model.ResourceStatusPlanning}, next, ownerID, fencingToken)
		cleanupCancel()
		if updateErr != nil {
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

	if err := s.store.SavePlanWithLease(ctx, resource, ownerID, fencingToken); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("persist terraform plan metadata: %w", err)
	}

	return resource, nil
}

func (s *ProvisioningService) Apply(
	ctx context.Context,
	id uuid.UUID,
	approvedPlanHash string,
) (model.InfrastructureResource, error) {
	execCtx, releaseOwnership, ownerID, fencingToken, err := s.acquireExecutionOwnership(ctx, id, "apply")
	if err != nil {
		return model.InfrastructureResource{}, err
	}
	defer releaseOwnership()

	resource, err := s.store.GetByID(execCtx, id)
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
		if updateErr := s.store.InvalidatePlan(ctx, resource, "apply", model.ResourceStatusFailed); updateErr != nil {
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
		if updateErr := s.store.InvalidatePlan(ctx, resource, "apply", model.ResourceStatusFailed); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("verify terraform plan: %v; persist failed status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	if !equalHash(actualHash, resource.PlanHash) {
		if updateErr := s.store.InvalidatePlan(ctx, resource, "apply", model.ResourceStatusFailed); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("%w; persist failed status: %v", ErrPlanHashMismatch, updateErr)
		}

		return model.InfrastructureResource{}, ErrPlanHashMismatch
	}

	if err := s.store.ClaimReviewedPlan(ctx, resource, "apply", identity.FromContext(ctx).Subject); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for apply: %w", err)
	}
	resource.Status = model.ResourceStatusProvisioning

	var applyErr error
	resource.LastExecutionError = ""
	if runner, ok := s.runner.(interface {
		ApplyWithState(context.Context, model.InfrastructureResource) (string, error)
	}); ok {
		var stateID string
		stateID, applyErr = runner.ApplyWithState(ctx, resource)
		if stateID != "" {
			resource.TerraformResourceID = stateID
			if applyErr == nil {
				verified := s.clock().UTC()
				resource.AWSLastVerifiedAt = &verified
			}
		}
	} else {
		applyErr = s.runner.Apply(ctx, resource)
	}
	if applyErr != nil {
		err := applyErr
		resource.LastExecutionError = "Apply did not complete or could not be verified. Reconciliation required."
		if updateErr := s.finishPlan(ctx, resource, "apply", model.ResourceStatusFailed, false, ownerID, fencingToken); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("terraform apply failed: %v; persist failed status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	if provider, ok := s.runner.(interface {
		EC2Attribution(context.Context, model.InfrastructureResource) *model.EC2Attribution
	}); ok {
		resource.EC2Attribution = provider.EC2Attribution(ctx, resource)
	}
	if err := s.finishPlan(ctx, resource, "apply", model.ResourceStatusActive, true, ownerID, fencingToken); err != nil {
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
	execCtx, releaseOwnership, ownerID, fencingToken, err := s.acquireExecutionOwnership(ctx, id, "plan_destroy")
	if err != nil {
		return model.InfrastructureResource{}, err
	}
	defer releaseOwnership()

	resource, err := s.store.GetByID(execCtx, id)
	if err != nil {
		return model.InfrastructureResource{}, err
	}

	if resource.Status != model.ResourceStatusActive &&
		resource.Status != model.ResourceStatusAwaitingDestroyApproval &&
		resource.Status != model.ResourceStatusDestroyFailed &&
		resource.Status != model.ResourceStatusFailed {
		return model.InfrastructureResource{}, fmt.Errorf(
			"%w: current status=%s",
			ErrInvalidProvisioningState,
			resource.Status,
		)
	}

	restoreStatus := model.ResourceStatusActive
	if resource.Status == model.ResourceStatusDestroyFailed || resource.Status == model.ResourceStatusFailed {
		restoreStatus = resource.Status
	}
	// Compare the revision when replacing a saved destroy plan.
	if resource.Status == model.ResourceStatusAwaitingDestroyApproval {
		err = s.store.InvalidatePlan(ctx, resource, "destroy", model.ResourceStatusPlanning)
	} else {
		err = s.store.TransitionStatus(ctx, id, []model.ResourceStatus{resource.Status}, model.ResourceStatusPlanning)
	}
	if err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for destroy planning: %w", err)
	}
	resource.Status = model.ResourceStatusPlanning

	result, err := s.runner.PlanDestroy(ctx, resource)
	if err != nil {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
		updateErr := s.store.TransitionStatusWithLease(cleanupCtx, id,
			[]model.ResourceStatus{model.ResourceStatusPlanning}, restoreStatus, ownerID, fencingToken)
		cleanupCancel()
		if updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("terraform destroy plan failed: %v; restore prior status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	now := result.PlanCreatedAt
	if now.IsZero() {
		now = s.clock().UTC()
	}

	approvalExpiresAt := now.Add(defaultApprovalTTL)

	resource.DestroyRequestedBy = identity.FromContext(ctx).Subject
	resource.DestroyPlanPath = result.PlanPath
	resource.DestroyPlanHash = result.PlanHash
	resource.ApprovalExpiresAt = &approvalExpiresAt
	resource.Status = model.ResourceStatusAwaitingDestroyApproval

	if err := s.store.SaveDestroyPlanWithLease(ctx, resource, ownerID, fencingToken); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("persist terraform destroy plan metadata: %w", err)
	}

	return resource, nil
}

// ApplyDestroy runs the approved destroy plan. It requires an unexpired
// approval window and a caller-supplied hash matching the stored plan hash and
// the plan file on disk. A failed execution requires operator reconciliation.
func (s *ProvisioningService) ApplyDestroy(
	ctx context.Context,
	id uuid.UUID,
	approvedPlanHash string,
) (model.InfrastructureResource, error) {
	execCtx, releaseOwnership, ownerID, fencingToken, err := s.acquireExecutionOwnership(ctx, id, "apply_destroy")
	if err != nil {
		return model.InfrastructureResource{}, err
	}
	defer releaseOwnership()

	resource, err := s.store.GetByID(execCtx, id)
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
		if updateErr := s.store.InvalidatePlan(ctx, resource, "destroy", model.ResourceStatusActive); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("%w; restore resource status: %v", cause, updateErr)
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

	if err := s.store.ClaimReviewedPlan(ctx, resource, "destroy", identity.FromContext(ctx).Subject); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("claim resource for destroy: %w", err)
	}
	resource.Status = model.ResourceStatusDestroying

	resource.LastExecutionError = ""
	if err := s.runner.ApplyDestroy(ctx, resource); err != nil {
		resource.LastExecutionError = "Destroy did not complete or state is not empty. Reconciliation required."
		if updateErr := s.finishPlan(ctx, resource, "destroy", model.ResourceStatusDestroyFailed, false, ownerID, fencingToken); updateErr != nil {
			return model.InfrastructureResource{}, fmt.Errorf("terraform destroy failed: %v; persist reconciliation-required status: %w", err, updateErr)
		}

		return model.InfrastructureResource{}, err
	}

	if err := s.finishPlan(ctx, resource, "destroy", model.ResourceStatusDestroyed, true, ownerID, fencingToken); err != nil {
		return model.InfrastructureResource{}, fmt.Errorf("persist destroyed status: %w", err)
	}
	resource.Status = model.ResourceStatusDestroyed

	return resource, nil
}

func (s *ProvisioningService) finishPlan(ctx context.Context, resource model.InfrastructureResource, operation string, next model.ResourceStatus, succeeded bool, ownerID string, fencingToken int64) error {
	writeCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	return s.store.FinishReviewedPlanWithLease(writeCtx, resource, operation, next, succeeded, ownerID, fencingToken)
}

func (s *ProvisioningService) Review(ctx context.Context, id uuid.UUID, input model.PlanReviewInput) error {
	caller := identity.FromContext(ctx)
	if !caller.Human() || (caller.Role != "platform-engineer" &&
		(caller.Role != "developer" || input.Action != "submit" || input.Operation != "apply")) {
		return ErrReviewDenied
	}
	if (input.Operation != "apply" && input.Operation != "destroy") ||
		(input.Action != "submit" && input.Action != "approve" && input.Action != "reject") ||
		input.Revision.IsZero() || input.PlanHash == "" {
		return repository.ErrResourceConflict
	}
	if input.Action == "approve" {
		resource, err := s.store.GetByID(ctx, id)
		if err != nil {
			return err
		}
		path := resource.PlanPath
		if input.Operation == "destroy" {
			path = resource.DestroyPlanPath
		}
		actual, err := hashFile(path)
		if err != nil || !equalHash(actual, input.PlanHash) {
			return ErrPlanHashMismatch
		}
	}
	return s.store.ReviewPlan(ctx, id, input, caller.Subject)
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

	reviews, err := s.store.PlanReviews(ctx, id)
	if err != nil {
		return model.PlanDetails{}, err
	}
	if resource.PlanHash == "" && resource.DestroyPlanHash == "" && len(reviews) == 0 {
		return model.PlanDetails{}, errors.New("no plan exists for resource")
	}

	now := s.clock().UTC()
	isExpired := false
	if resource.ApprovalExpiresAt != nil {
		isExpired = !now.Before(*resource.ApprovalExpiresAt)
	}

	planHash := resource.PlanHash
	operation, requester := "apply", resource.RequestedBy
	summary := resource.PlanSummary
	if resource.Status == model.ResourceStatusAwaitingDestroyApproval ||
		(resource.Status != model.ResourceStatusAwaitingApproval && len(reviews) > 0 && reviews[0].Operation == "destroy") {
		planHash = resource.DestroyPlanHash
		operation, requester = "destroy", resource.DestroyRequestedBy
		if resource.DestroyPlanPath != "" {
			if data, err := os.ReadFile(resource.DestroyPlanPath + ".summary"); err == nil && len(data) > 0 {
				summary = string(data)
			}
		}
	} else {
		if summary == "" && resource.PlanPath != "" {
			if data, err := os.ReadFile(resource.PlanPath + ".summary"); err == nil && len(data) > 0 {
				summary = string(data)
			}
		}
	}

	var pricing *model.PlanPricingBasis
	if operation == "apply" && resource.Status == model.ResourceStatusAwaitingApproval && !isExpired {
		pricing = terraform.PlanPricingBasis(resource)
	}
	return model.PlanDetails{
		PricingBasis:      pricing,
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
		ProjectID:         resource.ProjectID, Requester: requester, Operation: operation, Revision: resource.UpdatedAt, Reviews: reviews,
	}, nil
}

func canStartPlan(status model.ResourceStatus) bool {
	switch status {
	case model.ResourceStatusPending,
		model.ResourceStatusFailed,
		model.ResourceStatusPlanning:
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
