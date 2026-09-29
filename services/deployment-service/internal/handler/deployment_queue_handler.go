package handler

import (
	"errors"
	"net/http"
	"strings"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/worker"
)

const (
	cloudForgeActorHeader       = "X-CloudForge-Actor"
	cloudForgeIncidentHeader    = "X-CloudForge-Incident"
	cloudForgeRemediationHeader = "X-CloudForge-Remediation"

	cloudForgeHumanApproved = "human-approved"
)

type DeploymentJobSubmitter interface {
	Submit(job worker.Job) error
}

type QueuedDeploymentHandler struct {
	queueManager service.DeploymentQueueManager
	submitter    DeploymentJobSubmitter
}

func NewQueuedDeploymentHandler(
	queueManager service.DeploymentQueueManager,
	submitter DeploymentJobSubmitter,
) *QueuedDeploymentHandler {
	return &QueuedDeploymentHandler{
		queueManager: queueManager,
		submitter:    submitter,
	}
}

func authorizeRemediationRequest(r *http.Request) error {
	actor := strings.TrimSpace(
		r.Header.Get(cloudForgeActorHeader),
	)

	if actor == "" {
		return errors.New("missing remediation actor")
	}

	incidentID := strings.TrimSpace(
		r.Header.Get(cloudForgeIncidentHeader),
	)

	if incidentID == "" {
		return errors.New("missing remediation incident")
	}

	remediation := strings.TrimSpace(
		r.Header.Get(cloudForgeRemediationHeader),
	)

	if remediation != cloudForgeHumanApproved {
		return errors.New("remediation authorization required")
	}

	return nil
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
	if err := authorizeRemediationRequest(r); err != nil {
		writeError(
			w,
			http.StatusForbidden,
			"remediation authorization required",
		)
		return
	}

	h.queue(w, r)
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

	err = h.submitter.Submit(
		worker.Job{
			ID:           uuid.New(),
			DeploymentID: deploymentID,
		},
	)

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

	writeJSON(
		w,
		http.StatusAccepted,
		map[string]interface{}{
			"message":       "deployment queued successfully",
			"deployment_id": deploymentID,
		},
	)
}
