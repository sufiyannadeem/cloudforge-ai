package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAuthorizeRemediationRequest(t *testing.T) {
	tests := []struct {
		name        string
		actor       string
		incidentID  string
		remediation string
		wantErr     bool
	}{
		{
			name:        "valid human approved remediation",
			actor:       "aiops-operator",
			incidentID:  "incident-123",
			remediation: "human-approved",
			wantErr:     false,
		},
		{
			name:        "missing actor",
			actor:       "",
			incidentID:  "incident-123",
			remediation: "human-approved",
			wantErr:     true,
		},
		{
			name:        "whitespace actor",
			actor:       "   ",
			incidentID:  "incident-123",
			remediation: "human-approved",
			wantErr:     true,
		},
		{
			name:        "missing incident",
			actor:       "aiops-operator",
			incidentID:  "",
			remediation: "human-approved",
			wantErr:     true,
		},
		{
			name:        "whitespace incident",
			actor:       "aiops-operator",
			incidentID:  "   ",
			remediation: "human-approved",
			wantErr:     true,
		},
		{
			name:        "missing remediation authorization",
			actor:       "aiops-operator",
			incidentID:  "incident-123",
			remediation: "",
			wantErr:     true,
		},
		{
			name:        "wrong remediation authorization",
			actor:       "aiops-operator",
			incidentID:  "incident-123",
			remediation: "ai-generated",
			wantErr:     true,
		},
		{
			name:        "case-sensitive remediation authorization",
			actor:       "aiops-operator",
			incidentID:  "incident-123",
			remediation: "Human-Approved",
			wantErr:     true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/api/v1/deployments/00000000-0000-0000-0000-000000000001/remediation-run",
				nil,
			)

			if tt.actor != "" {
				request.Header.Set(
					cloudForgeActorHeader,
					tt.actor,
				)
			}

			if tt.incidentID != "" {
				request.Header.Set(
					cloudForgeIncidentHeader,
					tt.incidentID,
				)
			}

			if tt.remediation != "" {
				request.Header.Set(
					cloudForgeRemediationHeader,
					tt.remediation,
				)
			}

			err := authorizeRemediationRequest(request)

			if tt.wantErr && err == nil {
				t.Fatal("expected authorization error")
			}

			if !tt.wantErr && err != nil {
				t.Fatalf(
					"expected authorization to succeed, got %v",
					err,
				)
			}
		})
	}
}

func TestQueuedDeploymentHandlerRejectsUnauthorizedRemediationRequestBeforeQueue(t *testing.T) {
	handler := NewQueuedDeploymentHandler(
		nil,
		nil,
	)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/deployments/00000000-0000-0000-0000-000000000001/remediation-run",
		nil,
	)

	request.SetPathValue(
		"id",
		"00000000-0000-0000-0000-000000000001",
	)

	response := httptest.NewRecorder()

	handler.RunRemediation(response, request)

	if response.Code != http.StatusForbidden {
		t.Fatalf(
			"expected HTTP %d, got %d",
			http.StatusForbidden,
			response.Code,
		)
	}
}

func TestQueuedDeploymentHandlerNormalRunDoesNotRequireRemediationAuthorization(t *testing.T) {
	handler := NewQueuedDeploymentHandler(
		nil,
		nil,
	)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/deployments/not-a-uuid/run",
		nil,
	)

	request.SetPathValue(
		"id",
		"not-a-uuid",
	)

	response := httptest.NewRecorder()

	handler.Run(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected HTTP %d for invalid deployment ID, got %d",
			http.StatusBadRequest,
			response.Code,
		)
	}
}
