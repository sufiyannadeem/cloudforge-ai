package handler

import (
	"net/http"
)

func NewRouter(h *DeploymentHandler) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", h.Health)

	mux.HandleFunc("POST /api/v1/deployments", h.Create)
	mux.HandleFunc("GET /api/v1/deployments", h.List)
	mux.HandleFunc("GET /api/v1/deployments/{id}", h.GetByID)
	mux.HandleFunc("PATCH /api/v1/deployments/{id}", h.Update)
	mux.HandleFunc("DELETE /api/v1/deployments/{id}", h.Delete)

	return mux
}
