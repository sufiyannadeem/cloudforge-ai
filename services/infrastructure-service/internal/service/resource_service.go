package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
)

type ResourceService struct {
	store repository.ResourceStore
}

func NewResourceService(store repository.ResourceStore) *ResourceService {
	return &ResourceService{
		store: store,
	}
}

func (s *ResourceService) Create(
	ctx context.Context,
	input model.CreateResourceInput,
) (model.InfrastructureResource, error) {
	if err := validateCreateInput(input); err != nil {
		return model.InfrastructureResource{}, err
	}

	now := time.Now().UTC()

	resource := model.InfrastructureResource{
		ID:                 uuid.New(),
		Name:               strings.TrimSpace(input.Name),
		Description:        strings.TrimSpace(input.Description),
		Provider:           input.Provider,
		Region:             strings.TrimSpace(input.Region),
		Environment:        strings.TrimSpace(input.Environment),
		Status:             model.ResourceStatusActive,
		TerraformDirectory: strings.TrimSpace(input.TerraformDirectory),
		CreatedAt:          now,
		UpdatedAt:          now,
	}

	if err := s.store.Create(ctx, resource); err != nil {
		return model.InfrastructureResource{}, err
	}

	return resource, nil
}

func (s *ResourceService) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	if id == uuid.Nil {
		return model.InfrastructureResource{}, errors.New("resource ID cannot be empty")
	}

	return s.store.GetByID(ctx, id)
}

func (s *ResourceService) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.InfrastructureResource, error) {
	if limit <= 0 {
		limit = 20
	}

	if limit > 100 {
		limit = 100
	}

	if offset < 0 {
		offset = 0
	}

	return s.store.List(ctx, limit, offset)
}

func (s *ResourceService) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateResourceInput,
) (model.InfrastructureResource, error) {
	if id == uuid.Nil {
		return model.InfrastructureResource{}, errors.New("resource ID cannot be empty")
	}

	resource, err := s.store.GetByID(ctx, id)
	if err != nil {
		return model.InfrastructureResource{}, err
	}

	if input.Name != nil {
		name := strings.TrimSpace(*input.Name)

		if len(name) < 3 || len(name) > 100 {
			return model.InfrastructureResource{}, errors.New(
				"name must contain between 3 and 100 characters",
			)
		}

		resource.Name = name
	}

	if input.Description != nil {
		resource.Description = strings.TrimSpace(*input.Description)
	}

	if input.Region != nil {
		region := strings.TrimSpace(*input.Region)

		if region == "" {
			return model.InfrastructureResource{}, errors.New(
				"region cannot be empty",
			)
		}

		resource.Region = region
	}

	if input.Environment != nil {
		environment := strings.TrimSpace(*input.Environment)

		if environment == "" {
			return model.InfrastructureResource{}, errors.New(
				"environment cannot be empty",
			)
		}

		resource.Environment = environment
	}

	if input.Status != nil {
		if !input.Status.IsValid() {
			return model.InfrastructureResource{}, errors.New(
				"invalid resource status",
			)
		}

		resource.Status = *input.Status
	}

	if input.TerraformDirectory != nil {
		directory := strings.TrimSpace(*input.TerraformDirectory)

		if directory == "" {
			return model.InfrastructureResource{}, errors.New(
				"terraform directory cannot be empty",
			)
		}

		resource.TerraformDirectory = directory
	}

	resource.UpdatedAt = time.Now().UTC()

	if err := s.store.Update(ctx, resource); err != nil {
		return model.InfrastructureResource{}, err
	}

	return resource, nil
}

func (s *ResourceService) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if id == uuid.Nil {
		return errors.New("resource ID cannot be empty")
	}

	return s.store.Delete(ctx, id)
}

func validateCreateInput(input model.CreateResourceInput) error {
	name := strings.TrimSpace(input.Name)

	if len(name) < 3 || len(name) > 100 {
		return errors.New(
			"name must contain between 3 and 100 characters",
		)
	}

	if !input.Provider.IsValid() {
		return fmt.Errorf("invalid provider: %s", input.Provider)
	}

	if strings.TrimSpace(input.Region) == "" {
		return errors.New("region cannot be empty")
	}

	if strings.TrimSpace(input.Environment) == "" {
		return errors.New("environment cannot be empty")
	}

	if strings.TrimSpace(input.TerraformDirectory) == "" {
		return errors.New("terraform directory cannot be empty")
	}

	return nil
}
