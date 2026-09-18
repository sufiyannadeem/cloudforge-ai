package model

import "testing"

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
