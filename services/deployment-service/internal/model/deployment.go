package model

import (
	"time"

	"github.com/google/uuid"
)

type DeploymentStatus string

const (
	DeploymentStatusPending   DeploymentStatus = "pending"
	DeploymentStatusQueued    DeploymentStatus = "queued"
	DeploymentStatusRunning   DeploymentStatus = "running"
	DeploymentStatusSucceeded DeploymentStatus = "succeeded"
	DeploymentStatusFailed    DeploymentStatus = "failed"
	DeploymentStatusCancelled DeploymentStatus = "cancelled"
)

func (s DeploymentStatus) IsValid() bool {
	switch s {
	case DeploymentStatusPending,
		DeploymentStatusQueued,
		DeploymentStatusRunning,
		DeploymentStatusSucceeded,
		DeploymentStatusFailed,
		DeploymentStatusCancelled:
		return true
	default:
		return false
	}
}

type Deployment struct {
	ID           uuid.UUID        `json:"id"`
	ProjectID    uuid.UUID        `json:"project_id"`
	Environment  string           `json:"environment"`
	Image        string           `json:"image"`
	GitCommitSHA string           `json:"git_commit_sha"`
	Namespace    string           `json:"namespace"`
	Status       DeploymentStatus `json:"status"`
	CreatedAt    time.Time        `json:"created_at"`
	UpdatedAt    time.Time        `json:"updated_at"`
}

type CreateDeploymentInput struct {
	ProjectID    uuid.UUID `json:"project_id"`
	Environment  string    `json:"environment"`
	Image        string    `json:"image"`
	GitCommitSHA string    `json:"git_commit_sha"`
	Namespace    string    `json:"namespace"`
}

type UpdateDeploymentInput struct {
	Environment  *string           `json:"environment,omitempty"`
	Image        *string           `json:"image,omitempty"`
	GitCommitSHA *string           `json:"git_commit_sha,omitempty"`
	Namespace    *string           `json:"namespace,omitempty"`
	Status       *DeploymentStatus `json:"status,omitempty"`
}
