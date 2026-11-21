package handler

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type rolloutSource interface {
	RolloutState(context.Context, uuid.UUID) (executor.RolloutState, error)
	Promote(context.Context, uuid.UUID, executor.RolloutState) error
}
type promotionStore interface {
	ClaimPromotion(context.Context, uuid.UUID, string, string) (uuid.UUID, error)
	CompletePromotion(context.Context, uuid.UUID, bool) error
	PromotionHistory(context.Context, uuid.UUID) ([]repository.PromotionAudit, error)
}
type RolloutHandler struct {
	Source rolloutSource
	Store  promotionStore
}

func (h *RolloutHandler) State(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "private, no-store")
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, 404, "deployment not found")
		return
	}
	if h.Source == nil || h.Store == nil {
		writeError(w, 503, "Argo Rollouts unavailable")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 12*time.Second)
	defer cancel()
	state, err := h.Source.RolloutState(ctx, id)
	if err != nil {
		writeError(w, 503, "verified Argo state unavailable; check prerequisites and revision ownership")
		return
	}
	history, err := h.Store.PromotionHistory(ctx, id)
	if err != nil {
		writeError(w, 503, "promotion audit unavailable")
		return
	}
	writeJSON(w, 200, map[string]any{"state": state, "history": history})
}
func (h *RolloutHandler) Promote(w http.ResponseWriter, r *http.Request) {
	caller := identity.FromContext(r.Context())
	if !caller.Human() || caller.Role != "platform-engineer" {
		writeError(w, 403, "Platform Engineer approval required")
		return
	}
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, 404, "deployment not found")
		return
	}
	if h.Source == nil || h.Store == nil {
		writeError(w, 503, "Argo Rollouts unavailable")
		return
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, 4097))
	digest := sha256.Sum256(body)
	if err != nil || len(body) > 4096 || caller.Body != hex.EncodeToString(digest[:]) || caller.Expiry <= time.Now().Unix() {
		writeError(w, 401, "fresh body-bound approval identity required")
		return
	}
	var input struct {
		UID             string `json:"uid"`
		ResourceVersion string `json:"resource_version"`
		Approve         bool   `json:"approve"`
	}
	if json.Unmarshal(body, &input) != nil || !input.Approve || input.UID == "" || input.ResourceVersion == "" {
		writeError(w, 400, "approve the exact preview revision")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()
	state, err := h.Source.RolloutState(ctx, id)
	if err != nil || state.UID != input.UID || state.ResourceVersion != input.ResourceVersion || !state.PromotionRequired || !state.PreviewReady || state.Phase != "Paused" {
		writeError(w, 409, "preview changed or is not ready; reload before approval")
		return
	}
	audit, err := h.Store.ClaimPromotion(ctx, id, input.UID, input.ResourceVersion)
	if err != nil {
		writeError(w, 409, "independent approval required, or promotion already claimed")
		return
	}
	err = h.Source.Promote(ctx, id, state)
	// Persist uncertainty even if the request disconnects. Never retry a consumed approval.
	auditCtx, auditCancel := context.WithTimeout(context.WithoutCancel(r.Context()), 5*time.Second)
	defer auditCancel()
	if saveErr := h.Store.CompletePromotion(auditCtx, audit, err == nil); saveErr != nil {
		writeError(w, 503, "promotion outcome unconfirmed; audit reconciliation required")
		return
	}
	if err != nil {
		writeError(w, 409, "promotion outcome uncertain; reconcile before further action")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "submitted", "message": "promotion submitted; Argo health still determines execution success"})
}
