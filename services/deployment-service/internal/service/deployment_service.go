package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/workflow"
)

var (
	ErrInvalidProjectID = errors.New(
		"project ID is required",
	)

	ErrInvalidEnvironment = errors.New(
		"invalid environment",
	)

	ErrInvalidImage = errors.New(
		"image is required",
	)

	ErrInvalidGitCommitSHA = errors.New(
		"git commit SHA is required",
	)

	ErrInvalidNamespace = errors.New(
		"namespace is required",
	)

	ErrInvalidDeploymentStatus = errors.New(
		"invalid deployment status",
	)

	ErrInvalidDeploymentID = errors.New(
		"deployment ID is required",
	)

	ErrDeploymentNotPending = errors.New(
		"deployment is not pending",
	)

	ErrInvalidDeploymentTransition = errors.New(
		"invalid deployment status transition",
	)
)

type DeploymentService struct {
	store repository.DeploymentStore
}

func NewDeploymentService(
	store repository.DeploymentStore,
) *DeploymentService {
	return &DeploymentService{
		store: store,
	}
}

func (s *DeploymentService) Create(
	ctx context.Context,
	input model.CreateDeploymentInput,
) (model.Deployment, error) {
	if err := validateCreateInput(input); err != nil {
		return model.Deployment{}, err
	}

	now := time.Now().UTC()

	deployment := model.Deployment{
		ID:           uuid.New(),
		ProjectID:    input.ProjectID,
		Environment:  input.Environment,
		Image:        strings.TrimSpace(input.Image),
		GitCommitSHA: strings.TrimSpace(input.GitCommitSHA),
		Namespace:    strings.TrimSpace(input.Namespace),
		Status:       model.DeploymentStatusPending,
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	if err := s.store.Create(ctx, deployment); err != nil {
		return model.Deployment{}, fmt.Errorf(
			"create deployment: %w",
			err,
		)
	}

	return deployment, nil
}

func (s *DeploymentService) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.Deployment, error) {
	if id == uuid.Nil {
		return model.Deployment{}, ErrInvalidDeploymentID
	}

	deployment, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.Deployment{}, fmt.Errorf(
			"get deployment: %w",
			err,
		)
	}

	return deployment, nil
}

func (s *DeploymentService) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.Deployment, error) {
	if limit <= 0 {
		limit = 20
	}

	if limit > 100 {
		limit = 100
	}

	if offset < 0 {
		offset = 0
	}

	deployments, err := s.store.List(
		ctx,
		limit,
		offset,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"list deployments: %w",
			err,
		)
	}

	return deployments, nil
}

func (s *DeploymentService) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateDeploymentInput,
) (model.Deployment, error) {
	if id == uuid.Nil {
		return model.Deployment{}, ErrInvalidDeploymentID
	}

	deployment, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.Deployment{}, fmt.Errorf(
			"get deployment for update: %w",
			err,
		)
	}

	if input.Environment != nil {
		if !isValidEnvironment(*input.Environment) {
			return model.Deployment{}, ErrInvalidEnvironment
		}

		deployment.Environment = *input.Environment
	}

	if input.Image != nil {
		if strings.TrimSpace(*input.Image) == "" {
			return model.Deployment{}, ErrInvalidImage
		}

		deployment.Image = strings.TrimSpace(*input.Image)
	}

	if input.GitCommitSHA != nil {
		if strings.TrimSpace(*input.GitCommitSHA) == "" {
			return model.Deployment{}, ErrInvalidGitCommitSHA
		}

		deployment.GitCommitSHA = strings.TrimSpace(
			*input.GitCommitSHA,
		)
	}

	if input.Namespace != nil {
		if strings.TrimSpace(*input.Namespace) == "" {
			return model.Deployment{}, ErrInvalidNamespace
		}

		deployment.Namespace = strings.TrimSpace(
			*input.Namespace,
		)
	}

	if input.Status != nil {
		if !input.Status.IsValid() {
			return model.Deployment{}, ErrInvalidDeploymentStatus
		}

		currentStatus := workflow.Status(
			deployment.Status,
		)

		requestedStatus := workflow.Status(
			*input.Status,
		)

		if currentStatus != requestedStatus {
			if err := workflow.ValidateTransition(
				currentStatus,
				requestedStatus,
			); err != nil {
				return model.Deployment{}, fmt.Errorf(
					"%w: %v",
					ErrInvalidDeploymentTransition,
					err,
				)
			}

			deployment.Status = *input.Status
		}
	}

	deployment.UpdatedAt = time.Now().UTC()

	if err := s.store.Update(ctx, deployment); err != nil {
		return model.Deployment{}, fmt.Errorf(
			"update deployment: %w",
			err,
		)
	}

	return deployment, nil
}

func (s *DeploymentService) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if id == uuid.Nil {
		return ErrInvalidDeploymentID
	}

	if err := s.store.Delete(ctx, id); err != nil {
		return fmt.Errorf(
			"delete deployment: %w",
			err,
		)
	}

	return nil
}

func validateCreateInput(
	input model.CreateDeploymentInput,
) error {
	if input.ProjectID == uuid.Nil {
		return ErrInvalidProjectID
	}

	if !isValidEnvironment(input.Environment) {
		return ErrInvalidEnvironment
	}

	if strings.TrimSpace(input.Image) == "" {
		return ErrInvalidImage
	}

	if strings.TrimSpace(input.GitCommitSHA) == "" {
		return ErrInvalidGitCommitSHA
	}

	if strings.TrimSpace(input.Namespace) == "" {
		return ErrInvalidNamespace
	}

	return nil
}

func isValidEnvironment(
	environment string,
) bool {
	switch environment {
	case "development", "staging", "production":
		return true
	default:
		return false
	}
}
func (s *DeploymentService) QueuePendingDeployment(
	ctx context.Context,
	id uuid.UUID,
) error {
	if id == uuid.Nil {
		return ErrInvalidDeploymentID
	}

	queueStore, ok := s.store.(deploymentQueueStore)
	if !ok {
		return errors.New(
			"deployment store does not support queue operations",
		)
	}

	if err := queueStore.ClaimPendingDeployment(
		ctx,
		id,
		time.Now().UTC(),
	); err != nil {
		return fmt.Errorf(
			"queue pending deployment: %w",
			err,
		)
	}

	return nil
}

func (s *DeploymentService) ReleaseQueuedDeployment(
	ctx context.Context,
	id uuid.UUID,
) error {
	if id == uuid.Nil {
		return ErrInvalidDeploymentID
	}

	queueStore, ok := s.store.(deploymentQueueStore)
	if !ok {
		return errors.New(
			"deployment store does not support queue operations",
		)
	}

	if err := queueStore.ReleaseQueuedDeployment(
		ctx,
		id,
		time.Now().UTC(),
	); err != nil {
		return fmt.Errorf(
			"release queued deployment: %w",
			err,
		)
	}

	return nil
}
