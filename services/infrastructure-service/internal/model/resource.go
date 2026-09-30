package model

import (
	"time"

	"github.com/google/uuid"
)

type Provider string

const (
	ProviderAWS   Provider = "aws"
	ProviderAzure Provider = "azure"
	ProviderGCP   Provider = "gcp"
	ProviderLocal Provider = "local"
)

func (p Provider) IsValid() bool {
	switch p {
	case ProviderAWS, ProviderAzure, ProviderGCP, ProviderLocal:
		return true
	default:
		return false
	}
}

type ResourceStatus string

const (
	ResourceStatusPending          ResourceStatus = "pending"
	ResourceStatusPlanning         ResourceStatus = "planning"
	ResourceStatusAwaitingApproval ResourceStatus = "awaiting_approval"
	ResourceStatusProvisioning     ResourceStatus = "provisioning"
	ResourceStatusActive           ResourceStatus = "active"
	ResourceStatusInactive         ResourceStatus = "inactive"
	ResourceStatusDestroying       ResourceStatus = "destroying"
	ResourceStatusFailed           ResourceStatus = "failed"
	ResourceStatusDestroyed        ResourceStatus = "destroyed"
)

func (s ResourceStatus) IsValid() bool {
	switch s {
	case ResourceStatusPending,
		ResourceStatusPlanning,
		ResourceStatusAwaitingApproval,
		ResourceStatusProvisioning,
		ResourceStatusActive,
		ResourceStatusInactive,
		ResourceStatusDestroying,
		ResourceStatusFailed,
		ResourceStatusDestroyed:
		return true
	default:
		return false
	}
}

type InfrastructureResource struct {
	ID                 uuid.UUID      `json:"id"`
	ProjectID          *uuid.UUID     `json:"project_id,omitempty"`
	Name               string         `json:"name"`
	Description        string         `json:"description,omitempty"`
	ResourceType       string         `json:"resource_type"`
	Provider           Provider       `json:"provider"`
	Region             string         `json:"region"`
	Environment        string         `json:"environment"`
	Configuration      map[string]any `json:"configuration"`
	Status             ResourceStatus `json:"status"`
	TerraformDirectory string         `json:"terraform_directory,omitempty"`
	PlanPath           string         `json:"plan_path,omitempty"`
	PlanHash           string         `json:"plan_hash,omitempty"`
	PlanCreatedAt      *time.Time     `json:"plan_created_at,omitempty"`
	ApprovalExpiresAt  *time.Time     `json:"approval_expires_at,omitempty"`
	CreatedAt          time.Time      `json:"created_at"`
	UpdatedAt          time.Time      `json:"updated_at"`
}

type CreateResourceInput struct {
	ProjectID          string         `json:"project_id"`
	Name               string         `json:"name"`
	Description        string         `json:"description"`
	ResourceType       string         `json:"resource_type"`
	Provider           Provider       `json:"provider"`
	Region             string         `json:"region"`
	Environment        string         `json:"environment"`
	Configuration      map[string]any `json:"configuration"`
	TerraformDirectory string         `json:"terraform_directory,omitempty"`
}

type UpdateResourceInput struct {
	Name               *string         `json:"name,omitempty"`
	Description        *string         `json:"description,omitempty"`
	Region             *string         `json:"region,omitempty"`
	Environment        *string         `json:"environment,omitempty"`
	Status             *ResourceStatus `json:"status,omitempty"`
	TerraformDirectory *string         `json:"terraform_directory,omitempty"`
	Configuration      map[string]any  `json:"configuration,omitempty"`
}

type ApplyResourceInput struct {
	PlanHash string `json:"plan_hash"`
}
