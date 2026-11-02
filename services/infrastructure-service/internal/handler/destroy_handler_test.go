package handler

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/service"
)

// serveDestroy routes through the real router so the new paths are covered.
func serveDestroy(
	provisioning *mockProvisioningManager,
	path string,
	body string,
) *httptest.ResponseRecorder {
	router := newResourceMux(newTestHandler(&mockResourceManager{}, provisioning))

	request := httptest.NewRequest(
		http.MethodPost,
		path,
		strings.NewReader(body),
	)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	return recorder
}

func TestDestroyPlanRoute(t *testing.T) {
	id := uuid.New()
	provisioning := &mockProvisioningManager{
		resource: model.InfrastructureResource{
			ID:     id,
			Status: model.ResourceStatusAwaitingDestroyApproval,
		},
	}

	recorder := serveDestroy(provisioning, "/api/v1/resources/"+id.String()+"/destroy/plan", "")

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	if provisioning.destroyPlanCallCount != 1 || provisioning.lastDestroyPlanID != id {
		t.Fatalf("expected one destroy plan call for %s", id)
	}

	if provisioning.destroyApplyCallCount != 0 {
		t.Fatal("destroy plan must never trigger destroy apply")
	}
}

func TestDestroyPlanErrorMapping(t *testing.T) {
	tests := []struct {
		name   string
		err    error
		status int
	}{
		{"not found", repository.ErrResourceNotFound, http.StatusNotFound},
		{"invalid state", service.ErrInvalidProvisioningState, http.StatusConflict},
		{"internal", errors.New("terraform exploded"), http.StatusInternalServerError},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			id := uuid.New()
			provisioning := &mockProvisioningManager{destroyPlanError: tt.err}

			recorder := serveDestroy(provisioning, "/api/v1/resources/"+id.String()+"/destroy/plan", "")

			if recorder.Code != tt.status {
				t.Fatalf("expected %d, got %d", tt.status, recorder.Code)
			}
		})
	}
}

func TestDestroyPlanInvalidUUID(t *testing.T) {
	provisioning := &mockProvisioningManager{}

	recorder := serveDestroy(provisioning, "/api/v1/resources/not-a-uuid/destroy/plan", "")

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", recorder.Code)
	}

	if provisioning.destroyPlanCallCount != 0 {
		t.Fatal("service must not be called for an invalid UUID")
	}
}

func TestDestroyApplyRoutePassesPlanHash(t *testing.T) {
	id := uuid.New()
	provisioning := &mockProvisioningManager{
		resource: model.InfrastructureResource{ID: id, Status: model.ResourceStatusDestroyed},
	}

	recorder := serveDestroy(
		provisioning,
		"/api/v1/resources/"+id.String()+"/destroy/apply",
		`{"plan_hash":"abc123"}`,
	)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}

	if provisioning.lastDestroyApplyID != id || provisioning.lastDestroyPlanHash != "abc123" {
		t.Fatalf("unexpected apply call: id=%s hash=%q", provisioning.lastDestroyApplyID, provisioning.lastDestroyPlanHash)
	}
}

func TestDestroyApplyRejectsBadBodies(t *testing.T) {
	id := uuid.New()

	for name, body := range map[string]string{
		"invalid json":  `{`,
		"unknown field": `{"plan_hash":"x","force":true}`,
	} {
		t.Run(name, func(t *testing.T) {
			provisioning := &mockProvisioningManager{}

			recorder := serveDestroy(provisioning, "/api/v1/resources/"+id.String()+"/destroy/apply", body)

			if recorder.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d", recorder.Code)
			}

			if provisioning.destroyApplyCallCount != 0 {
				t.Fatal("service must not be called for an invalid body")
			}
		})
	}
}

func TestDestroyApplyErrorMapping(t *testing.T) {
	tests := []struct {
		name   string
		err    error
		status int
	}{
		{"not found", repository.ErrResourceNotFound, http.StatusNotFound},
		{"invalid state", service.ErrInvalidProvisioningState, http.StatusConflict},
		{"expired", service.ErrApprovalExpired, http.StatusConflict},
		{"hash mismatch", service.ErrPlanHashMismatch, http.StatusConflict},
		{"internal", errors.New("terraform exploded"), http.StatusInternalServerError},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			id := uuid.New()
			provisioning := &mockProvisioningManager{destroyApplyError: tt.err}

			recorder := serveDestroy(
				provisioning,
				"/api/v1/resources/"+id.String()+"/destroy/apply",
				`{"plan_hash":"abc"}`,
			)

			if recorder.Code != tt.status {
				t.Fatalf("expected %d, got %d", tt.status, recorder.Code)
			}
		})
	}
}
