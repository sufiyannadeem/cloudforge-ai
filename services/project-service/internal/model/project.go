package model

import (
	"time"

	"github.com/google/uuid"
)

type ProjectStatus string

const (
	ProjectStatusActive   ProjectStatus = "active"
	ProjectStatusInactive ProjectStatus = "inactive"
	ProjectStatusArchived ProjectStatus = "archived"
)

type Project struct {
	ID            uuid.UUID     `json:"id"`
	Name          string        `json:"name"`
	Description   *string       `json:"description,omitempty"`
	RepositoryURL string        `json:"repository_url"`
	DefaultBranch string        `json:"default_branch"`
	Status        ProjectStatus `json:"status"`
	CreatedAt     time.Time     `json:"created_at"`
	UpdatedAt     time.Time     `json:"updated_at"`
}

type CreateProjectInput struct {
	Name          string  `json:"name"`
	Description   *string `json:"description,omitempty"`
	RepositoryURL string  `json:"repository_url"`
	DefaultBranch string  `json:"default_branch,omitempty"`
}

type UpdateProjectInput struct {
	Name          *string        `json:"name,omitempty"`
	Description   *string        `json:"description,omitempty"`
	RepositoryURL *string        `json:"repository_url,omitempty"`
	DefaultBranch *string        `json:"default_branch,omitempty"`
	Status        *ProjectStatus `json:"status,omitempty"`
}
