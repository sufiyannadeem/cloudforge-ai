package handler

import (
	"net/http"
	"strings"

	"github.com/google/uuid"
	apidocs "github.com/sufiyannadeem/cloudforge-ai-deployment-service/docs"

	identity "github.com/sufiyannadeem/cloudforge-service-identity"
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
	telemetryHandlers ...*ProjectTelemetryHandler,
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

	if len(telemetryHandlers) > 0 {
		telemetry := telemetryHandlers[0]
		mux.HandleFunc("GET /api/v1/deployments/{id}/logs", telemetry.Logs)
		mux.HandleFunc("GET /api/v1/deployments/{id}/observability", telemetry.Health)
		mux.HandleFunc("GET /api/v1/deployments/{id}/diagnostics", telemetry.Diagnostics)
		mux.HandleFunc("POST /api/v1/deployments/{id}/diagnostics", telemetry.Diagnostics)
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

// NewAuthenticatedRouter checks the caller and enforces deployment permissions.
func NewAuthenticatedRouter(mux http.Handler, frontendKey, aiopsKey string, scopes ...identity.ProjectAccess) http.Handler {
	var access identity.ProjectAccess
	if len(scopes) != 0 {
		access = scopes[0]
	}
	keys := map[string]string{"frontend": frontendKey, "aiops": aiopsKey}
	if frontendKey == aiopsKey {
		keys = nil
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet && (r.URL.Path == "/health" ||
			r.URL.Path == "/metrics" || r.URL.Path == "/docs" ||
			strings.HasPrefix(r.URL.Path, "/docs/") || r.URL.Path == "/openapi.yaml") {
			mux.ServeHTTP(w, r)
			return
		}
		caller, ok := identity.Verify(r, "deployment", keys)
		if !ok {
			writeError(w, http.StatusUnauthorized, "service identity required")
			return
		}
		path, _ := strings.CutPrefix(r.URL.Path, "/api/v1/deployments/")
		isRemediation := strings.HasSuffix(path, "/remediation-run")
		allowed := caller.Human() && !isRemediation &&
			(r.Method != http.MethodDelete || caller.Role == "platform-engineer")
		if caller.Issuer == "aiops" && caller.Service() {
			id, suffix, _ := strings.Cut(path, "/")
			_, err := uuid.Parse(id)
			allowed = (r.Method == http.MethodGet && r.URL.Path == "/api/v1/deployments") || err == nil && ((r.Method == http.MethodGet && (suffix == "" || suffix == "attempts")) ||
				(r.Method == http.MethodPost && suffix == "remediation-run"))
		}
		if !allowed {
			writeError(w, http.StatusForbidden, "insufficient deployment permissions")
			return
		}
		scopedRequest := access.Attach(identity.WithClaims(r, caller))
		if caller.Human() && strings.HasPrefix(r.URL.Path, "/api/v1/deployments/") {
			idText, action, _ := strings.Cut(path, "/")
			id, err := uuid.Parse(idText)
			if err != nil {
				writeError(w, http.StatusNotFound, "deployment not found")
				return
			}
			diagnosticCapture := r.Method == http.MethodPost && action == "diagnostics"
			write := r.Method != http.MethodGet && r.Method != http.MethodHead && !diagnosticCapture
			if err := access.Resource(scopedRequest.Context(), "deployment", id.String(), write); err != nil {
				writeError(w, identity.AccessStatus(err), "deployment access denied")
				return
			}
		}
		mux.ServeHTTP(w, scopedRequest)
		// Forward the registered pattern to the outer metrics middleware.
		r.Pattern = scopedRequest.Pattern
	})
}
