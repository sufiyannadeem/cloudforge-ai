package model

import (
	"github.com/google/uuid"
	"time"
)

type PlanReviewInput struct {
	Action    string    `json:"action"`
	Operation string    `json:"operation"`
	PlanHash  string    `json:"plan_hash"`
	Revision  time.Time `json:"revision"`
}

type PlanReview struct {
	Operation          string     `json:"operation"`
	Revision           time.Time  `json:"revision"`
	PlanHash           string     `json:"plan_hash"`
	ProjectID          uuid.UUID  `json:"project_id"`
	Environment        string     `json:"environment"`
	Requester          string     `json:"requester"`
	SubmittedBy        string     `json:"submitted_by"`
	SubmittedAt        time.Time  `json:"submitted_at"`
	ExpiresAt          time.Time  `json:"expires_at"`
	Status             string     `json:"status"`
	DecidedBy          *string    `json:"decided_by,omitempty"`
	DecidedAt          *time.Time `json:"decided_at,omitempty"`
	ExecutedBy         *string    `json:"executed_by,omitempty"`
	ExecutionStartedAt *time.Time `json:"execution_started_at,omitempty"`
	FinishedAt         *time.Time `json:"finished_at,omitempty"`
}
