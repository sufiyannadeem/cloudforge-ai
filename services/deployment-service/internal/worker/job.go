package worker

import "github.com/google/uuid"

// Job represents a deployment task.
type Job struct {
	ID           uuid.UUID
	DeploymentID uuid.UUID
}
