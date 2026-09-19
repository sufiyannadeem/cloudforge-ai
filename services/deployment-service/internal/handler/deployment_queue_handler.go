package handler

import (
	"context"
	"errors"
	"net/http"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/worker"
)

// DeploymentJobSubmitter submits deployment jobs to a worker queue.
type DeploymentJobSubmitter interface {
	Submit(job worker.Job) error
}

// QueuedDeploymentHandler handles deployment execution requests.
type QueuedDeploymentHandler struct {
	service   service.DeploymentManager
	submitter DeploymentJobSubmitter
}

// NewQueuedDeploymentHandler creates a queued deployment handler.
func NewQueuedDeploymentHandler(
	deploymentService service.DeploymentManager,
	submitter DeploymentJobSubmitter,
) *QueuedDeploymentHandler {
	return &QueuedDeploymentHandler{
		service:   deploymentService,
		submitter: submitter,
	}
}

// Run queues an existing deployment for execution.
func (h *QueuedDeploymentHandler) Run(
	w http.ResponseWriter,
	r *http.Request,
) {
	idValue := r.PathValue("id")

	deploymentID, err := uuid.Parse(idValue)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid deployment ID")
		return
	}

	deployment, err := h.service.GetByID(
		context.Background(),
		deploymentID,
	)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	if deployment.Status != model.DeploymentStatusPending {
		writeError(
			w,
			http.StatusConflict,
			"only pending deployments can be queued",
		)
		return
	}

	err = h.submitter.Submit(worker.Job{
		ID:           uuid.New(),
		DeploymentID: deploymentID,
	})
	if err != nil {
		if errors.Is(err, worker.ErrQueueClosed) {
			writeError(
				w,
				http.StatusServiceUnavailable,
				"deployment worker queue is closed",
			)
			return
		}

		writeError(
			w,
			http.StatusServiceUnavailable,
			"failed to queue deployment",
		)
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]interface{}{
		"message":       "deployment queued successfully",
		"deployment_id": deploymentID,
	})
}
