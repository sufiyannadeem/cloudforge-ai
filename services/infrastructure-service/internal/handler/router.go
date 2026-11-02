package handler

import (
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"strings"
)

// NewRouterWithInternalToken protects every API route with a server-to-server
// credential while keeping the health endpoint available to container probes.
// The token must be generated and shared through the deployment secret manager.
func NewRouterWithInternalToken(resourceHandler *ResourceHandler, token string) http.Handler {
	mux := newResourceMux(resourceHandler)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet && r.URL.Path == "/health" {
			mux.ServeHTTP(w, r)
			return
		}
		provided := strings.TrimSpace(r.Header.Get("X-CloudForge-Internal-Token"))
		if len(token) < 32 || len(provided) != len(token) ||
			subtle.ConstantTimeCompare([]byte(provided), []byte(token)) != 1 {
			writeAuthorizationError(w, http.StatusUnauthorized, "service authentication required")
			return
		}
		if !authorizedInfrastructureRequest(r) {
			writeAuthorizationError(w, http.StatusForbidden, "insufficient infrastructure permissions")
			return
		}
		mux.ServeHTTP(w, r)
	})
}

func authorizedInfrastructureRequest(r *http.Request) bool {
	role := strings.ToLower(strings.TrimSpace(r.Header.Get("X-CloudForge-Role")))
	validRole := role == "viewer" || role == "devops" || role == "sre" ||
		role == "platform-engineer" || role == "admin"
	if !validRole {
		return false
	}
	if r.Method == http.MethodGet || r.Method == http.MethodHead {
		return true
	}
	if strings.TrimSpace(r.Header.Get("X-CloudForge-Actor")) == "" {
		return false
	}
	if r.Method == http.MethodDelete || strings.HasSuffix(r.URL.Path, "/apply") {
		return role == "platform-engineer" || role == "admin"
	}
	return role == "platform-engineer" || role == "devops" || role == "sre" || role == "admin"
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

	mux.HandleFunc("GET /health", resourceHandler.Health)

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
		resourceHandler.Plan,
	)

	mux.HandleFunc(
		"GET /api/v1/resources/{id}/plan",
		resourceHandler.GetPlan,
	)

	mux.HandleFunc(
		"POST /api/v1/resources/{id}/apply",
		resourceHandler.Apply,
	)

	mux.HandleFunc(
		"POST /api/v1/resources/{id}/destroy/plan",
		resourceHandler.PlanDestroy,
	)

	mux.HandleFunc(
		"POST /api/v1/resources/{id}/destroy/apply",
		resourceHandler.ApplyDestroy,
	)

	return mux
}
