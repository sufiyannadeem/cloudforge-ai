package model

import "testing"

func TestDeploymentStatusIsValid(t *testing.T) {
	validStatuses := []DeploymentStatus{
		DeploymentStatusPending,
		DeploymentStatusQueued,
		DeploymentStatusRunning,
		DeploymentStatusSucceeded,
		DeploymentStatusFailed,
		DeploymentStatusCancelled,
	}

	for _, status := range validStatuses {
		if !status.IsValid() {
			t.Errorf("expected status %q to be valid", status)
		}
	}
}

func TestDeploymentStatusRejectsInvalidValue(t *testing.T) {
	status := DeploymentStatus("unknown")

	if status.IsValid() {
		t.Fatal("expected unknown status to be invalid")
	}
}
