package repository

import (
	"context"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type DeploymentAttemptStore interface {
	Create(
		ctx context.Context,
		attempt model.DeploymentAttempt,
	) error

	Update(
		ctx context.Context,
		attempt model.DeploymentAttempt,
	) error

	GetNextAttemptNumber(
		ctx context.Context,
		deploymentID uuid.UUID,
	) (int, error)

	ListByDeploymentID(
		ctx context.Context,
		deploymentID uuid.UUID,
		limit int,
		offset int,
	) ([]model.DeploymentAttempt, error)
}
