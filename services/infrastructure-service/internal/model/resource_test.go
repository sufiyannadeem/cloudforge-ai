package model

import (
	"encoding/json"
	"testing"
)

func TestProviderIsValid(t *testing.T) {
	validProviders := []Provider{
		ProviderAWS,
		ProviderAzure,
		ProviderGCP,
		ProviderLocal,
	}

	for _, provider := range validProviders {
		if !provider.IsValid() {
			t.Errorf("expected provider %q to be valid", provider)
		}
	}
}

func TestProviderIsInvalid(t *testing.T) {
	invalidProviders := []Provider{
		"",
		"unknown",
		"aws-lambda",
	}

	for _, provider := range invalidProviders {
		if provider.IsValid() {
			t.Errorf("expected provider %q to be invalid", provider)
		}
	}
}

func TestResourceStatusIsValid(t *testing.T) {
	validStatuses := []ResourceStatus{
		ResourceStatusActive,
		ResourceStatusInactive,
		ResourceStatusProvisioning,
		ResourceStatusDestroying,
		ResourceStatusFailed,
	}

	for _, status := range validStatuses {
		if !status.IsValid() {
			t.Errorf("expected status %q to be valid", status)
		}
	}
}

func TestResourceStatusIsInvalid(t *testing.T) {
	invalidStatuses := []ResourceStatus{
		"",
		"unknown",
		"running",
		"deleted",
	}

	for _, status := range invalidStatuses {
		if status.IsValid() {
			t.Errorf("expected status %q to be invalid", status)
		}
	}
}

func TestActiveWorkflowDoesNotClaimLiveAWSVerification(t *testing.T) {
	resource := InfrastructureResource{Status: ResourceStatusActive, Provider: ProviderAWS,
		EC2Attribution: &EC2Attribution{InstanceID: "private-state-id"}}
	body, err := json.Marshal(resource)
	if err != nil {
		t.Fatal(err)
	}
	var response map[string]any
	if err := json.Unmarshal(body, &response); err != nil {
		t.Fatal(err)
	}
	if response["status"] != "active" || response["status_source"] != "terraform_workflow" ||
		response["aws_live_status"] != "unverified" || response["EC2Attribution"] != nil {
		t.Fatalf("unexpected workflow status metadata")
	}
}
