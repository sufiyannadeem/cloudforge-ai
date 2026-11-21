package handler

import (
	"context"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
)

type remediationClaimFunc func(context.Context, uuid.UUID, string, string, string) error

func (f remediationClaimFunc) ClaimRemediation(ctx context.Context, target uuid.UUID, proposal, incident, dispatch string) error {
	return f(ctx, target, proposal, incident, dispatch)
}

func TestRemediationRunRequiresPersistedApproval(t *testing.T) {
	const internal = testAIOpsKey
	target := uuid.New()
	dispatch := base64.RawURLEncoding.EncodeToString(make([]byte, 32))
	for _, tc := range []struct {
		name       string
		token      string
		proof      string
		claimErr   error
		status     int
		wantClaims int
	}{
		{name: "missing service authentication", proof: dispatch, status: http.StatusUnauthorized},
		{name: "legacy approval headers", token: internal, status: http.StatusForbidden},
		{name: "unrecognized persisted approval", token: internal, proof: dispatch, claimErr: repository.ErrRemediationApprovalRequired, status: http.StatusForbidden, wantClaims: 1},
		{name: "verified dispatch", token: internal, proof: dispatch, status: http.StatusAccepted, wantClaims: 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			claims := 0
			h := NewQueuedDeploymentHandler(nil, nil, remediationClaimFunc(
				func(_ context.Context, got uuid.UUID, proposal, incident, proof string) error {
					claims++
					if got != target || proposal != "proposal-1" || incident != "incident-1" || proof != dispatch {
						t.Fatal("approval was not bound to the exact request")
					}
					return tc.claimErr
				},
			))
			mux := http.NewServeMux()
			RegisterDeploymentRunRoute(mux, h)
			req := httptest.NewRequest(http.MethodPost, "/api/v1/deployments/"+target.String()+"/remediation-run", nil)
			if tc.token != "" {
				signDeploymentRequest(req, "aiops", tc.token, "")
			}
			req.Header.Set("X-CloudForge-Actor", "claimed-human")
			req.Header.Set("X-CloudForge-Remediation", "human-approved")
			req.Header.Set("X-CloudForge-Proposal", "proposal-1")
			req.Header.Set("X-CloudForge-Incident", "incident-1")
			req.Header.Set("X-CloudForge-Dispatch", tc.proof)
			res := httptest.NewRecorder()
			NewAuthenticatedRouter(mux, testFrontendKey, internal).ServeHTTP(res, req)
			if res.Code != tc.status || claims != tc.wantClaims {
				t.Fatalf("got HTTP %d and %d claims", res.Code, claims)
			}
		})
	}
}

func TestQueuedDeploymentHandlerNormalRunDoesNotRequireRemediationAuthorization(t *testing.T) {
	handler := NewQueuedDeploymentHandler(nil, nil, nil)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/deployments/not-a-uuid/run", nil)
	request.SetPathValue("id", "not-a-uuid")
	response := httptest.NewRecorder()
	handler.Run(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("expected HTTP %d, got %d", http.StatusBadRequest, response.Code)
	}
}
