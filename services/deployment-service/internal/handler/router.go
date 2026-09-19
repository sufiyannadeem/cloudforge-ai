package handler

import (
	"net/http"

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
	mux.HandleFunc(
		"POST /api/v1/deployments/{id}/run",
		h.Run,
	)
}
