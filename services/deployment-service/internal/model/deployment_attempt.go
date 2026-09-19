package model

import (
	"time"

	"github.com/google/uuid"
)

type DeploymentAttemptStatus string

const (
	AttemptStatusRunning   DeploymentAttemptStatus = "running"
	AttemptStatusSucceeded DeploymentAttemptStatus = "succeeded"
	AttemptStatusFailed    DeploymentAttemptStatus = "failed"
	AttemptStatusCancelled DeploymentAttemptStatus = "cancelled"
)

func (s DeploymentAttemptStatus) IsValid() bool {
	switch s {
	case AttemptStatusRunning,
		AttemptStatusSucceeded,
		AttemptStatusFailed,
		AttemptStatusCancelled:
		return true
	default:
		return false
	}
}

type DeploymentAttempt struct {
	ID            uuid.UUID               `json:"id"`
	DeploymentID  uuid.UUID               `json:"deployment_id"`
	AttemptNumber int                     `json:"attempt_number"`
	Status        DeploymentAttemptStatus `json:"status"`
	ErrorMessage  *string                 `json:"error_message,omitempty"`
	StartedAt     time.Time               `json:"started_at"`
	CompletedAt   *time.Time              `json:"completed_at,omitempty"`
	DurationMs    *int64                  `json:"duration_ms,omitempty"`
	CreatedAt     time.Time               `json:"created_at"`
}
