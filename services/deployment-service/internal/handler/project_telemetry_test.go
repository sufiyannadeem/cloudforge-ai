package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func TestTelemetryRejectsCallerSelectors(t *testing.T) {
	handler := NewProjectTelemetryHandler(nil, "")
	for _, tc := range []struct {
		query string
		call  http.HandlerFunc
		want  int
	}{
		{"namespace=foreign", handler.Logs, 400},
		{"container=foreign", handler.Logs, 400},
		{"page=0;pod=foreign", handler.Logs, 400},
		{"page=0&page=1", handler.Logs, 400},
		{"lines=201", handler.Logs, 400},
		{"page=24", handler.Logs, 400},
		{"query=up", handler.Health, 400},
		{"page=0&lines=200", handler.Logs, 503},
	} {
		t.Run(tc.query, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, "/?"+tc.query, nil)
			request.SetPathValue("id", uuid.NewString())
			response := httptest.NewRecorder()
			tc.call(response, request)
			if response.Code != tc.want {
				t.Fatalf("status = %d, want %d", response.Code, tc.want)
			}
		})
	}
}

func TestDiagnosticsRejectUntrustedIdentityAndSelectors(t *testing.T) {
	handler := NewProjectTelemetryHandler(nil, "")
	req := httptest.NewRequest(http.MethodPost, "/?namespace=foreign&pod=arbitrary", nil)
	req.SetPathValue("id", uuid.NewString())
	response := httptest.NewRecorder()
	handler.Diagnostics(response, req)
	if response.Code != http.StatusForbidden {
		t.Fatalf("unverified caller received %d", response.Code)
	}
	req = identity.WithClaims(req, identity.Claims{Issuer: "frontend", Subject: "developer", Role: "developer"})
	response = httptest.NewRecorder()
	handler.Diagnostics(response, req)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("caller-controlled diagnostic selectors received %d", response.Code)
	}
}
