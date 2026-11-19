package handler

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type diagnosticStore interface {
	SaveDiagnostic(context.Context, uuid.UUID, string, json.RawMessage) (repository.DiagnosticCapture, error)
	DiagnosticHistory(context.Context, uuid.UUID) ([]repository.DiagnosticCapture, error)
}

func (h *ProjectTelemetryHandler) Diagnostics(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "private, no-store")
	caller := identity.FromContext(r.Context())
	if !caller.Human() || caller.Subject == "" {
		writeError(w, http.StatusForbidden, "human identity required")
		return
	}
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, http.StatusNotFound, "deployment not found")
		return
	}
	if r.URL.RawQuery != "" {
		writeError(w, http.StatusBadRequest, "diagnostic selectors are managed by the service")
		return
	}
	if h.diagnostics == nil {
		writeError(w, http.StatusServiceUnavailable, "diagnostic history unavailable")
		return
	}
	if r.Method == http.MethodGet {
		history, err := h.diagnostics.DiagnosticHistory(r.Context(), id)
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "diagnostic history unavailable")
			return
		}
		writeJSON(w, http.StatusOK, history)
		return
	}

	source, ok := h.source.(interface {
		DiagnoseProject(context.Context, uuid.UUID) (executor.ProjectDiagnosis, error)
	})
	if !ok {
		writeError(w, http.StatusServiceUnavailable, "verified Kubernetes diagnostics unavailable")
		return
	}
	report, err := source.DiagnoseProject(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "verified Kubernetes diagnostics unavailable")
		return
	}
	raw, err := json.Marshal(report)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "diagnostic evidence unavailable")
		return
	}
	item, err := h.diagnostics.SaveDiagnostic(r.Context(), id, caller.Subject, raw)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "diagnostic evidence could not be saved")
		return
	}
	writeJSON(w, http.StatusCreated, item)
}
