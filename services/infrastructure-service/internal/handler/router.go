package handler

import "net/http"

func NewRouter(resourceHandler *ResourceHandler) http.Handler {
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

	return mux
}
