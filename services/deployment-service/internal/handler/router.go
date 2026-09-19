package handler

import (
	"net/http"

	apidocs "github.com/sufiyannadeem/cloudforge-ai-deployment-service/docs"
)

func NewRouter(h *DeploymentHandler) http.Handler {
	return NewRouterWithQueue(h, nil)
}

func NewRouterWithQueue(
	h *DeploymentHandler,
	queuedHandler *QueuedDeploymentHandler,
) http.Handler {
	mux := http.NewServeMux()

	// Health endpoint.
	mux.HandleFunc("GET /health", h.Health)

	// Deployment API endpoints.
	mux.HandleFunc("POST /api/v1/deployments", h.Create)
	mux.HandleFunc("GET /api/v1/deployments", h.List)
	mux.HandleFunc("GET /api/v1/deployments/{id}", h.GetByID)
	mux.HandleFunc("PATCH /api/v1/deployments/{id}", h.Update)
	mux.HandleFunc("DELETE /api/v1/deployments/{id}", h.Delete)

	// Deployment execution endpoint.
	if queuedHandler != nil {
		RegisterDeploymentRunRoute(mux, queuedHandler)
	}

	// Swagger UI.
	mux.HandleFunc("GET /docs", func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		http.Redirect(w, r, "/docs/", http.StatusPermanentRedirect)
	})

	mux.Handle(
		"GET /docs/",
		http.StripPrefix(
			"/docs/",
			http.FileServer(http.FS(apidocs.Files)),
		),
	)

	// OpenAPI specification.
	mux.HandleFunc("GET /openapi.yaml", func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		w.Header().Set("Content-Type", "application/yaml")

		http.ServeFileFS(
			w,
			r,
			apidocs.Files,
			"openapi.yaml",
		)
	})

	return mux
}

func RegisterDeploymentRunRoute(
	mux *http.ServeMux,
	h *QueuedDeploymentHandler,
) {
	mux.HandleFunc(
		"POST /api/v1/deployments/{id}/run",
		h.Run,
	)
}
