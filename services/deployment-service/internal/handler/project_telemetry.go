package handler

import (
	"context"
	"net/http"
	"net/url"
	"strconv"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
)

type projectTelemetrySource interface {
	ProjectLogs(context.Context, uuid.UUID, int, int) (executor.ProjectLogs, error)
	ProjectHealth(context.Context, uuid.UUID, string) (executor.ProjectHealth, error)
}

type ProjectTelemetryHandler struct {
	source        projectTelemetrySource
	prometheusURL string
	diagnostics   diagnosticStore
}

func NewProjectTelemetryHandler(source projectTelemetrySource, prometheusURL string, stores ...diagnosticStore) *ProjectTelemetryHandler {
	handler := &ProjectTelemetryHandler{source: source, prometheusURL: prometheusURL}
	if len(stores) > 0 {
		handler.diagnostics = stores[0]
	}
	return handler
}

func (h *ProjectTelemetryHandler) Logs(w http.ResponseWriter, r *http.Request) {
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, http.StatusNotFound, "deployment not found")
		return
	}
	page, lines := 0, 100
	query, err := url.ParseQuery(r.URL.RawQuery)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid log selector")
		return
	}
	for key, values := range query {
		if len(values) != 1 || (key != "page" && key != "lines") {
			writeError(w, http.StatusBadRequest, "invalid log selector")
			return
		}
		value, err := strconv.Atoi(values[0])
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid log selector")
			return
		}
		if key == "page" {
			page = value
		} else {
			lines = value
		}
	}
	if page < 0 || page >= 24 || lines < 1 || lines > 200 {
		writeError(w, http.StatusBadRequest, "invalid log page or line limit")
		return
	}
	if h.source == nil {
		writeError(w, http.StatusServiceUnavailable, "verified deployment logs unavailable")
		return
	}
	logs, err := h.source.ProjectLogs(r.Context(), id, page, lines)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "verified deployment logs unavailable")
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, http.StatusOK, logs)
}

func (h *ProjectTelemetryHandler) Health(w http.ResponseWriter, r *http.Request) {
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, http.StatusNotFound, "deployment not found")
		return
	}
	if r.URL.RawQuery != "" {
		writeError(w, http.StatusBadRequest, "metric selectors are managed by the service")
		return
	}
	if h.source == nil {
		writeError(w, http.StatusServiceUnavailable, "verified deployment metrics unavailable")
		return
	}
	health, err := h.source.ProjectHealth(r.Context(), id, h.prometheusURL)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "verified deployment metrics unavailable")
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, http.StatusOK, health)
}
