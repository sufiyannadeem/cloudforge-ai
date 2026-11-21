package handler

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func (h *ResourceHandler) Drift(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	caller := identity.FromContext(ctx)
	if !caller.Human() || (r.Method == http.MethodPost && caller.Role != "platform-engineer" && caller.Role != "sre") {
		writeError(w, http.StatusForbidden, "drift access denied")
		return
	}
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid resource ID")
		return
	}
	if h.DriftStore == nil || h.DriftRunner == nil {
		writeError(w, http.StatusServiceUnavailable, "drift scanning unavailable")
		return
	}
	resource, err := h.resourceManager.GetByID(ctx, id)
	if errors.Is(err, repository.ErrResourceNotFound) {
		writeError(w, http.StatusNotFound, "resource not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "resource unavailable")
		return
	}
	if r.Method == http.MethodGet {
		history, err := h.DriftStore.DriftHistory(ctx, id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "drift history unavailable")
			return
		}
		writeJSON(w, http.StatusOK, history)
		return
	}
	if resource.Status != model.ResourceStatusActive {
		writeError(w, http.StatusConflict, "drift scans require an active resource")
		return
	}

	findings, err := h.DriftRunner.ScanDrift(ctx, resource)
	scan := repository.DriftScan{Actor: caller.Subject, Status: "observed"}
	if err != nil {
		scan.Status = "unavailable"
	}
	scan.Findings, _ = json.Marshal(findings)
	scan, err = h.DriftStore.RecordDrift(ctx, id, resource.UpdatedAt, scan)
	if errors.Is(err, repository.ErrResourceConflict) {
		writeError(w, http.StatusConflict, "resource changed during scan")
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "could not record drift scan")
	} else {
		writeJSON(w, http.StatusCreated, scan)
	}
}
