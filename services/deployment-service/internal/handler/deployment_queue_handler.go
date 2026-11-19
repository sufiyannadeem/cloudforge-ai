package handler

import (
	"context"
	"encoding/base64"
	"errors"
	"net/http"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/worker"

	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type RemediationClaimer interface {
	ClaimRemediation(context.Context, uuid.UUID, string, string, string) error
}

type DeploymentJobSubmitter interface {
	Submit(job worker.Job) error
}

type QueuedDeploymentHandler struct {
	queueManager service.DeploymentQueueManager
	submitter    DeploymentJobSubmitter
	remediation  RemediationClaimer
}

func NewQueuedDeploymentHandler(
	queueManager service.DeploymentQueueManager,
	submitter DeploymentJobSubmitter,
	remediation RemediationClaimer,
) *QueuedDeploymentHandler {
	return &QueuedDeploymentHandler{
		queueManager: queueManager,
		submitter:    submitter,
		remediation:  remediation,
	}
}

// Run is the normal deployment execution endpoint.
//
// IMPORTANT:
// This endpoint intentionally does NOT require remediation headers.
// Normal deployment workflows must continue to work without
// CloudForge remediation authorization metadata.
func (h *QueuedDeploymentHandler) Run(
	w http.ResponseWriter,
	r *http.Request,
) {
	h.queue(w, r)
}

// RunRemediation is the controlled remediation execution endpoint.
//
// Only explicitly human-approved AIOps remediation requests may use
// this endpoint.
func (h *QueuedDeploymentHandler) RunRemediation(
	w http.ResponseWriter,
	r *http.Request,
) {
	caller := identity.FromContext(r.Context())
	if caller.Issuer != "aiops" || !caller.Service() {
		writeError(w, http.StatusUnauthorized, "AIOps service identity required")
		return
	}

	target, err := uuid.Parse(r.PathValue("id"))
	if err != nil || target == uuid.Nil {
		writeError(w, http.StatusBadRequest, "invalid deployment ID")
		return
	}
	proposal := r.Header.Get("X-CloudForge-Proposal")
	incident := r.Header.Get("X-CloudForge-Incident")
	dispatch := r.Header.Get("X-CloudForge-Dispatch")
	decoded, decodeErr := base64.RawURLEncoding.Strict().DecodeString(dispatch)
	if proposal == "" || len(proposal) > 64 || incident == "" || len(incident) > 64 ||
		decodeErr != nil || len(decoded) != 32 || h.remediation == nil {
		writeError(w, http.StatusForbidden, "valid unused remediation approval required")
		return
	}

	err = h.remediation.ClaimRemediation(r.Context(), target, proposal, incident, dispatch)
	switch {
	case errors.Is(err, repository.ErrRemediationApprovalRequired):
		writeError(w, http.StatusForbidden, "valid unused remediation approval required")
	case err != nil:
		writeError(w, http.StatusServiceUnavailable, "remediation authorization unavailable")
	default:
		writeQueued(w, target)
	}
}

func (h *QueuedDeploymentHandler) queue(
	w http.ResponseWriter,
	r *http.Request,
) {
	deploymentID, err := uuid.Parse(
		r.PathValue("id"),
	)

	if err != nil {
		writeError(
			w,
			http.StatusBadRequest,
			"invalid deployment ID",
		)
		return
	}

	err = h.queueManager.QueuePendingDeployment(
		r.Context(),
		deploymentID,
	)

	if err != nil {
		switch {
		case errors.Is(
			err,
			service.ErrInvalidDeploymentID,
		):
			writeError(
				w,
				http.StatusBadRequest,
				"invalid deployment ID",
			)

		case errors.Is(
			err,
			repository.ErrDeploymentNotFound,
		):
			writeError(
				w,
				http.StatusNotFound,
				"deployment not found",
			)

		case errors.Is(
			err,
			service.ErrDeploymentNotPending,
		),
			errors.Is(
				err,
				repository.ErrDeploymentNotPending,
			):
			writeError(
				w,
				http.StatusConflict,
				"only pending deployments can be queued",
			)

		default:
			writeError(
				w,
				http.StatusInternalServerError,
				"failed to claim deployment",
			)
		}

		return
	}

	if h.submitter != nil {
		err = h.submitter.Submit(
			worker.Job{
				ID:           uuid.New(),
				DeploymentID: deploymentID,
			},
		)
	}

	if err != nil {
		rollbackErr := h.queueManager.ReleaseQueuedDeployment(
			r.Context(),
			deploymentID,
		)

		if rollbackErr != nil {
			writeError(
				w,
				http.StatusInternalServerError,
				"deployment claimed but rollback failed",
			)
			return
		}

		switch {
		case errors.Is(err, worker.ErrQueueFull):
			writeError(
				w,
				http.StatusServiceUnavailable,
				"deployment queue is full",
			)

		case errors.Is(err, worker.ErrQueueClosed):
			writeError(
				w,
				http.StatusServiceUnavailable,
				"deployment queue is closed",
			)

		default:
			writeError(
				w,
				http.StatusInternalServerError,
				"failed to queue deployment",
			)
		}

		return
	}

	writeQueued(w, deploymentID)
}

func writeQueued(w http.ResponseWriter, deploymentID uuid.UUID) {
	writeJSON(
		w,
		http.StatusAccepted,
		map[string]interface{}{
			"message":       "deployment queued successfully",
			"deployment_id": deploymentID,
		},
	)
}
