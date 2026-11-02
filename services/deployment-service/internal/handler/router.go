package handler

import (
	"crypto/subtle"
	"net/http"
	"strings"

	apidocs "github.com/sufiyannadeem/cloudforge-ai-deployment-service/docs"
)

func NewRouter(h *DeploymentHandler) http.Handler {
	return NewRouterWithDependenciesAndMetrics(
		h,
		nil,
		nil,
		nil,
	)
}

func NewRouterWithQueue(
	h *DeploymentHandler,
	queuedHandler *QueuedDeploymentHandler,
) http.Handler {
	return NewRouterWithDependenciesAndMetrics(
		h,
		queuedHandler,
		nil,
		nil,
	)
}

func NewRouterWithDependencies(
	h *DeploymentHandler,
	queuedHandler *QueuedDeploymentHandler,
	attemptHandler *DeploymentAttemptHandler,
) http.Handler {
	return NewRouterWithDependenciesAndMetrics(
		h,
		queuedHandler,
		attemptHandler,
		nil,
	)
}

func NewRouterWithDependenciesAndMetrics(
	h *DeploymentHandler,
	queuedHandler *QueuedDeploymentHandler,
	attemptHandler *DeploymentAttemptHandler,
	metricsHandler http.Handler,
) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", h.Health)

	mux.HandleFunc(
		"POST /api/v1/deployments",
		h.Create,
	)

	mux.HandleFunc(
		"GET /api/v1/deployments",
		h.List,
	)

	mux.HandleFunc(
		"GET /api/v1/deployments/{id}",
		h.GetByID,
	)

	mux.HandleFunc(
		"PATCH /api/v1/deployments/{id}",
		h.Update,
	)

	mux.HandleFunc(
		"DELETE /api/v1/deployments/{id}",
		h.Delete,
	)

	mux.HandleFunc(
		"POST /api/v1/deployments/{id}/rollback",
		h.Rollback,
	)

	if queuedHandler != nil {
		RegisterDeploymentRunRoute(
			mux,
			queuedHandler,
		)
	}

	if attemptHandler != nil {
		mux.HandleFunc(
			"GET /api/v1/deployments/{id}/attempts",
			attemptHandler.ListByDeploymentID,
		)
	}

	mux.HandleFunc(
		"GET /docs",
		func(
			w http.ResponseWriter,
			r *http.Request,
		) {
			http.Redirect(
				w,
				r,
				"/docs/",
				http.StatusPermanentRedirect,
			)
		},
	)

	mux.Handle(
		"GET /docs/",
		http.StripPrefix(
			"/docs/",
			http.FileServer(
				http.FS(apidocs.Files),
			),
		),
	)

	mux.HandleFunc(
		"GET /openapi.yaml",
		func(
			w http.ResponseWriter,
			r *http.Request,
		) {
			w.Header().Set(
				"Content-Type",
				"application/yaml",
			)

			http.ServeFileFS(
				w,
				r,
				apidocs.Files,
				"openapi.yaml",
			)
		},
	)

	if metricsHandler != nil {
		mux.Handle(
			"GET /metrics",
			metricsHandler,
		)
	}

	return mux
}

func RegisterDeploymentRunRoute(
	mux *http.ServeMux,
	h *QueuedDeploymentHandler,
) {
	// Normal deployment execution.
	mux.HandleFunc(
		"POST /api/v1/deployments/{id}/run",
		h.Run,
	)

	// Controlled AIOps remediation execution.
	mux.HandleFunc(
		"POST /api/v1/deployments/{id}/remediation-run",
		h.RunRemediation,
	)
}

// NewRouterWithInternalToken protects all deployment API routes with a server-to-server
// token and role-based access control, matching least-privilege principles.
func NewRouterWithInternalToken(mux http.Handler, token string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Public endpoints: health probes, docs, metrics
		if r.Method == http.MethodGet && (r.URL.Path == "/health" ||
			r.URL.Path == "/metrics" ||
			r.URL.Path == "/docs" ||
			strings.HasPrefix(r.URL.Path, "/docs/") ||
			r.URL.Path == "/openapi.yaml") {
			mux.ServeHTTP(w, r)
			return
		}

		provided := strings.TrimSpace(r.Header.Get("X-CloudForge-Internal-Token"))
		if len(token) < 32 || len(provided) != len(token) ||
			subtle.ConstantTimeCompare([]byte(provided), []byte(token)) != 1 {
			writeError(w, http.StatusUnauthorized, "service authentication required")
			return
		}

		if !authorizedDeploymentRequest(r) {
			writeError(w, http.StatusForbidden, "insufficient deployment permissions")
			return
		}

		mux.ServeHTTP(w, r)
	})
}

func authorizedDeploymentRequest(r *http.Request) bool {
	role := strings.ToLower(strings.TrimSpace(r.Header.Get("X-CloudForge-Role")))
	validRole := role == "viewer" || role == "devops" || role == "sre" ||
		role == "platform-engineer" || role == "admin"
	if !validRole {
		return false
	}

	if r.Method == http.MethodGet || r.Method == http.MethodHead {
		return true
	}

	actor := strings.TrimSpace(r.Header.Get("X-CloudForge-Actor"))
	if actor == "" {
		return false
	}

	// Least privilege: DELETE requires platform-engineer or admin
	if r.Method == http.MethodDelete {
		return role == "platform-engineer" || role == "admin"
	}

	// Normal mutations (POST, PATCH): devops, sre, platform-engineer, admin (viewer denied)
	return role == "platform-engineer" || role == "devops" || role == "sre" || role == "admin"
}
