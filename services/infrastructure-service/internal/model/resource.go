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
	ResourceStatusActive       ResourceStatus = "active"
	ResourceStatusInactive     ResourceStatus = "inactive"
	ResourceStatusProvisioning ResourceStatus = "provisioning"
	ResourceStatusDestroying   ResourceStatus = "destroying"
	ResourceStatusFailed       ResourceStatus = "failed"
)

func (s ResourceStatus) IsValid() bool {
	switch s {
	case ResourceStatusActive,
		ResourceStatusInactive,
		ResourceStatusProvisioning,
		ResourceStatusDestroying,
		ResourceStatusFailed:
		return true
	default:
		return false
	}
}

type InfrastructureResource struct {
	ID                 uuid.UUID      `json:"id"`
	Name               string         `json:"name"`
	Description        string         `json:"description,omitempty"`
	Provider           Provider       `json:"provider"`
	Region             string         `json:"region"`
	Environment        string         `json:"environment"`
	Status             ResourceStatus `json:"status"`
	TerraformDirectory string         `json:"terraform_directory"`
	CreatedAt          time.Time      `json:"created_at"`
	UpdatedAt          time.Time      `json:"updated_at"`
}

type CreateResourceInput struct {
	Name               string   `json:"name"`
	Description        string   `json:"description"`
	Provider           Provider `json:"provider"`
	Region             string   `json:"region"`
	Environment        string   `json:"environment"`
	TerraformDirectory string   `json:"terraform_directory"`
}

type UpdateResourceInput struct {
	Name               *string         `json:"name,omitempty"`
	Description        *string         `json:"description,omitempty"`
	Region             *string         `json:"region,omitempty"`
	Environment        *string         `json:"environment,omitempty"`
	Status             *ResourceStatus `json:"status,omitempty"`
	TerraformDirectory *string         `json:"terraform_directory,omitempty"`
}
