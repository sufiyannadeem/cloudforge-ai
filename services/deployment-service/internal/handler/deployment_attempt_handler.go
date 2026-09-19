package handler

import (
	"net/http"
	"strconv"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
)

type DeploymentAttemptHandler struct {
	deploymentService service.DeploymentManager
	attemptRepository repository.DeploymentAttemptStore
}

func NewDeploymentAttemptHandler(
	deploymentService service.DeploymentManager,
	attemptRepository repository.DeploymentAttemptStore,
) *DeploymentAttemptHandler {
	return &DeploymentAttemptHandler{
		deploymentService: deploymentService,
		attemptRepository: attemptRepository,
	}
}

func (h *DeploymentAttemptHandler) ListByDeploymentID(
	w http.ResponseWriter,
	r *http.Request,
) {
	deploymentID, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid deployment ID")
		return
	}

	_, err = h.deploymentService.GetByID(
		r.Context(),
		deploymentID,
	)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	limit := parseQueryInt(r, "limit", 20)
	offset := parseQueryInt(r, "offset", 0)

	attempts, err := h.attemptRepository.ListByDeploymentID(
		r.Context(),
		deploymentID,
		limit,
		offset,
	)
	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			"failed to list deployment attempts",
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"deployment_id": deploymentID,
		"attempts":      attempts,
		"limit":         limit,
		"offset":        offset,
	})
}

func parseQueryInt(
	r *http.Request,
	key string,
	defaultValue int,
) int {
	value := r.URL.Query().Get(key)
	if value == "" {
		return defaultValue
	}

	parsed, err := strconv.Atoi(value)
	if err != nil {
		return defaultValue
	}

	return parsed
}
