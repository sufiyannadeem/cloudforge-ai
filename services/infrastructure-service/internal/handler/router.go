package handler

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"github.com/google/uuid"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type ConsumeApprovalAssertion func(context.Context, identity.Claims) error

func NewAuthenticatedRouter(resourceHandler *ResourceHandler, frontendKey string, consume ConsumeApprovalAssertion, scopes ...identity.ProjectAccess) http.Handler {
	mux := newResourceMux(resourceHandler)
	var access identity.ProjectAccess
	if len(scopes) != 0 {
		access = scopes[0]
	}
	keys := map[string]string{"frontend": frontendKey}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet && r.URL.Path == "/health" {
			mux.ServeHTTP(w, r)
			return
		}
		caller, ok := identity.Verify(r, "infrastructure", keys)
		if !ok || !caller.Human() {
			writeAuthorizationError(w, http.StatusUnauthorized, "service and operator identity required")
			return
		}
		r = access.Attach(identity.WithClaims(r, caller))
		write := r.Method != http.MethodGet && r.Method != http.MethodHead
		parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
		if write && caller.Role != "platform-engineer" && !(caller.Role == "sre" && r.Method == http.MethodPost && len(parts) == 5 && parts[4] == "drift") {
			canRequestOrPlan := (r.URL.Path == "/api/v1/resources") ||
				(len(parts) == 5 && (parts[4] == "plan" || parts[4] == "review"))
			if caller.Role != "developer" || r.Method != http.MethodPost || !canRequestOrPlan {
				writeAuthorizationError(w, http.StatusForbidden, "insufficient infrastructure permissions")
				return
			}
		}
		if caller.Role == "developer" && len(parts) >= 4 {
			id, err := uuid.Parse(parts[3])
			if err != nil {
				writeAuthorizationError(w, http.StatusNotFound, "resource not found")
				return
			}
			if err := access.Resource(r.Context(), "infrastructure", id.String(), write); err != nil {
				writeAuthorizationError(w, identity.AccessStatus(err), "resource access denied")
				return
			}
		}
		if r.Method == http.MethodPost && (strings.HasSuffix(r.URL.Path, "/apply") || strings.HasSuffix(r.URL.Path, "/review")) {
			body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 65536))
			digest := sha256.Sum256(body)
			if err != nil || caller.Body != hex.EncodeToString(digest[:]) {
				writeAuthorizationError(w, http.StatusForbidden, "approval request does not match assertion")
				return
			}
			if consume == nil {
				writeAuthorizationError(w, http.StatusServiceUnavailable, "approval protection unavailable")
				return
			}
			if err := consume(r.Context(), caller); err != nil {
				if errors.Is(err, identity.ErrReplay) {
					writeAuthorizationError(w, http.StatusConflict, "approval assertion already used")
				} else {
					writeAuthorizationError(w, http.StatusServiceUnavailable, "approval protection unavailable")
				}
				return
			}
			r.Body = io.NopCloser(bytes.NewReader(body))
		}
		mux.ServeHTTP(w, r)
	})
}

func writeAuthorizationError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"error": map[string]string{"message": message},
	})
}

func newResourceMux(resourceHandler *ResourceHandler) http.Handler {
	mux := http.NewServeMux()
	terraformOperation := func(next http.HandlerFunc) http.HandlerFunc {
		if !resourceHandler.TerraformReadOnly {
			return next
		}
		return func(w http.ResponseWriter, _ *http.Request) {
			writeError(w, http.StatusServiceUnavailable, "Terraform execution is disabled in this environment")
		}
	}

	mux.HandleFunc("GET /health", resourceHandler.Health)
	mux.HandleFunc("GET /api/v1/resources/{id}/jobs/{job}", resourceHandler.JobStatus)

	mux.HandleFunc(
		"POST /api/v1/resources",
		resourceHandler.Create,
	)

	mux.HandleFunc(
		"GET /api/v1/resources",
		resourceHandler.List,
	)

	mux.HandleFunc(
		"GET /api/v1/resources/{id}",
		resourceHandler.GetByID,
	)

	mux.HandleFunc(
		"PATCH /api/v1/resources/{id}",
		resourceHandler.Update,
	)

	mux.HandleFunc(
		"DELETE /api/v1/resources/{id}",
		resourceHandler.Delete,
	)

	mux.HandleFunc(
		"POST /api/v1/resources/{id}/plan",
		terraformOperation(resourceHandler.asyncTerraform(resourceHandler.Plan)),
	)

	mux.HandleFunc(
		"GET /api/v1/resources/{id}/plan",
		resourceHandler.GetPlan,
	)

	mux.HandleFunc("POST /api/v1/resources/{id}/review", resourceHandler.Review)
	mux.HandleFunc("GET /api/v1/resources/{id}/drift", resourceHandler.Drift)
	mux.HandleFunc("POST /api/v1/resources/{id}/drift", terraformOperation(resourceHandler.Drift))

	mux.HandleFunc(
		"POST /api/v1/resources/{id}/apply",
		terraformOperation(resourceHandler.asyncTerraform(resourceHandler.Apply)),
	)

	mux.HandleFunc(
		"POST /api/v1/resources/{id}/destroy/plan",
		terraformOperation(resourceHandler.asyncTerraform(resourceHandler.PlanDestroy)),
	)

	mux.HandleFunc(
		"POST /api/v1/resources/{id}/destroy/apply",
		terraformOperation(resourceHandler.asyncTerraform(resourceHandler.ApplyDestroy)),
	)

	return mux
}
