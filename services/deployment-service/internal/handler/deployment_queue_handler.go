package handler

import (
	"errors"
	"net/http"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/worker"
)

type DeploymentJobSubmitter interface {
	Submit(job worker.Job) error
}

type QueuedDeploymentHandler struct {
	service   service.DeploymentManager
	submitter DeploymentJobSubmitter
}

func NewQueuedDeploymentHandler(
	deploymentService service.DeploymentManager,
	submitter DeploymentJobSubmitter,
) *QueuedDeploymentHandler {
	return &QueuedDeploymentHandler{
		service:   deploymentService,
		submitter: submitter,
	}
}

func (h *QueuedDeploymentHandler) Run(
	w http.ResponseWriter,
	r *http.Request,
) {
	deploymentID, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		writeError(
			w,
			http.StatusBadRequest,
			"invalid deployment ID",
		)
		return
	}

	deployment, err := h.service.GetByID(
		r.Context(),
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
