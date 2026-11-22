package model

import (
	"encoding/json"
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
	// ResourceStatusAwaitingDestroyApproval means a hashed destroy plan exists
	// and a human must approve it before terraform destroy is applied.
	ResourceStatusAwaitingDestroyApproval ResourceStatus = "awaiting_destroy_approval"
	ResourceStatusDestroyFailed           ResourceStatus = "destroy_failed"
	ResourceStatusFailed                  ResourceStatus = "failed"
	ResourceStatusDestroyed               ResourceStatus = "destroyed"
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
		ResourceStatusAwaitingDestroyApproval,
		ResourceStatusDestroyFailed,
		ResourceStatusFailed,
		ResourceStatusDestroyed:
		return true
	default:
		return false
	}
}

type EC2Attribution struct {
	AccountID  string
	InstanceID string
}

type InfrastructureResource struct {
	AWSLastVerifiedAt   *time.Time      `json:"aws_last_verified_at,omitempty"`
	TerraformResourceID string          `json:"terraform_resource_id,omitempty"`
	LastExecutionError  string          `json:"last_execution_error,omitempty"`
	EC2Attribution      *EC2Attribution `json:"-"`
	ID                  uuid.UUID       `json:"id"`
	ProjectID           *uuid.UUID      `json:"project_id,omitempty"`
	Name                string          `json:"name"`
	Description         string          `json:"description,omitempty"`
	ResourceType        string          `json:"resource_type"`
	Provider            Provider        `json:"provider"`
	Region              string          `json:"region"`
	Environment         string          `json:"environment"`
	Configuration       map[string]any  `json:"configuration"`
	Status              ResourceStatus  `json:"status"`
	TerraformDirectory  string          `json:"terraform_directory,omitempty"`
	PlanPath            string          `json:"plan_path,omitempty"`
	PlanHash            string          `json:"plan_hash,omitempty"`
	PlanCreatedAt       *time.Time      `json:"plan_created_at,omitempty"`
	PlanSummary         string          `json:"plan_summary,omitempty"`
	DestroyPlanPath     string          `json:"destroy_plan_path,omitempty"`
	DestroyPlanHash     string          `json:"destroy_plan_hash,omitempty"`
	ApprovalExpiresAt   *time.Time      `json:"approval_expires_at,omitempty"`
	RequestedBy         string          `json:"requested_by,omitempty"`
	DestroyRequestedBy  string          `json:"destroy_requested_by,omitempty"`
	ReviewStatus        string          `json:"review_status,omitempty"`
	CreatedAt           time.Time       `json:"created_at"`
	UpdatedAt           time.Time       `json:"updated_at"`
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

type PlanPricingBasis struct {
	ResourceType string `json:"resource_type"`
	Unit         string `json:"unit"`
	Quantity     int    `json:"quantity"`
}

type PlanDetails struct {
	PricingBasis      *PlanPricingBasis `json:"pricing_basis,omitempty"`
	ResourceID        uuid.UUID         `json:"resource_id"`
	ResourceName      string            `json:"resource_name"`
	ResourceType      string            `json:"resource_type"`
	Provider          Provider          `json:"provider"`
	Region            string            `json:"region"`
	Environment       string            `json:"environment"`
	Status            ResourceStatus    `json:"status"`
	PlanHash          string            `json:"plan_hash"`
	PlanCreatedAt     *time.Time        `json:"plan_created_at,omitempty"`
	ApprovalExpiresAt *time.Time        `json:"approval_expires_at,omitempty"`
	IsExpired         bool              `json:"is_expired"`
	PlanSummary       string            `json:"plan_summary"`
	ProjectID         *uuid.UUID        `json:"project_id,omitempty"`
	Requester         string            `json:"requester,omitempty"`
	Revision          time.Time         `json:"revision"`
	Operation         string            `json:"operation"`
	Reviews           []PlanReview      `json:"reviews"`
	Configuration     map[string]any    `json:"configuration"`
}

// MarshalJSON separates the workflow status from independent AWS observations.
func (r InfrastructureResource) MarshalJSON() ([]byte, error) {
	type resource InfrastructureResource
	var awsStatus string
	if r.Provider == ProviderAWS {
		awsStatus = "unverified"
	}
	return json.Marshal(struct {
		resource
		StatusSource  string `json:"status_source"`
		AWSLiveStatus string `json:"aws_live_status,omitempty"`
	}{resource(r), "terraform_workflow", awsStatus})
}

type ExecutionLease struct {
	ResourceID     uuid.UUID `json:"resource_id"`
	OwnerID        string    `json:"owner_id"`
	Operation      string    `json:"operation"`
	FencingToken   int64     `json:"fencing_token"`
	LeaseExpiresAt time.Time `json:"lease_expires_at"`
	AcquiredAt     time.Time `json:"acquired_at"`
	HeartbeatAt    time.Time `json:"heartbeat_at"`
}
