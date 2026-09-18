package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/service"
)

type DeploymentHandler struct {
	service service.DeploymentManager
}

func NewDeploymentHandler(
	deploymentService service.DeploymentManager,
) *DeploymentHandler {
	return &DeploymentHandler{
		service: deploymentService,
	}
}

func (h *DeploymentHandler) Health(
	w http.ResponseWriter,
	r *http.Request,
) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"service": "deployment-service",
	})
}

func (h *DeploymentHandler) Create(
	w http.ResponseWriter,
	r *http.Request,
) {
	var input model.CreateDeploymentInput

	if err := decodeJSON(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	deployment, err := h.service.Create(r.Context(), input)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusCreated, deployment)
}

func (h *DeploymentHandler) List(
	w http.ResponseWriter,
	r *http.Request,
) {
	limit, offset, err := parsePagination(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	deployments, err := h.service.List(
		r.Context(),
		limit,
		offset,
	)

	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"items":  deployments,
		"limit":  normalizeLimit(limit),
		"offset": normalizeOffset(offset),
	})
}

func (h *DeploymentHandler) GetByID(
	w http.ResponseWriter,
	r *http.Request,
) {
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	deployment, err := h.service.GetByID(r.Context(), id)
	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, deployment)
}

func (h *DeploymentHandler) Update(
	w http.ResponseWriter,
	r *http.Request,
) {
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var input model.UpdateDeploymentInput

	if err := decodeJSON(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	deployment, err := h.service.Update(
		r.Context(),
		id,
		input,
	)

	if err != nil {
		writeServiceError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, deployment)
}

func (h *DeploymentHandler) Delete(
	w http.ResponseWriter,
	r *http.Request,
) {
	id, err := parseDeploymentID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	if err := h.service.Delete(r.Context(), id); err != nil {
		writeServiceError(w, err)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func decodeJSON(
	r *http.Request,
	target interface{},
) error {
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()

	if err := decoder.Decode(target); err != nil {
		return errors.New("invalid JSON request body")
	}

	return nil
}

func parseDeploymentID(
	r *http.Request,
) (uuid.UUID, error) {
	idValue := r.PathValue("id")

	id, err := uuid.Parse(idValue)
	if err != nil {
		return uuid.Nil, errors.New("invalid deployment ID")
	}

	return id, nil
}

func parsePagination(
	r *http.Request,
) (int, int, error) {
	limit := 0
	offset := 0

	if value := r.URL.Query().Get("limit"); value != "" {
		parsedLimit, err := strconv.Atoi(value)
		if err != nil {
			return 0, 0, errors.New("limit must be a valid integer")
		}

		if parsedLimit < 1 || parsedLimit > 100 {
			return 0, 0, errors.New("limit must be between 1 and 100")
		}

		limit = parsedLimit
	}

	if value := r.URL.Query().Get("offset"); value != "" {
		parsedOffset, err := strconv.Atoi(value)
		if err != nil {
			return 0, 0, errors.New("offset must be a valid integer")
		}

		if parsedOffset < 0 {
			return 0, 0, errors.New("offset cannot be negative")
		}

		offset = parsedOffset
	}

	return limit, offset, nil
}

func normalizeLimit(limit int) int {
	if limit <= 0 {
		return 20
	}

	return limit
}

func normalizeOffset(offset int) int {
	if offset < 0 {
		return 0
	}

	return offset
}

func writeServiceError(
	w http.ResponseWriter,
	err error,
) {
	switch {
	case errors.Is(err, repository.ErrDeploymentNotFound):
		writeError(w, http.StatusNotFound, "deployment not found")

	case errors.Is(err, service.ErrInvalidProjectID),
		errors.Is(err, service.ErrInvalidEnvironment),
		errors.Is(err, service.ErrInvalidImage),
		errors.Is(err, service.ErrInvalidGitCommitSHA),
		errors.Is(err, service.ErrInvalidNamespace),
		errors.Is(err, service.ErrInvalidDeploymentStatus),
		errors.Is(err, service.ErrInvalidDeploymentID):
		writeError(w, http.StatusBadRequest, err.Error())

	default:
		writeError(w, http.StatusInternalServerError, "internal server error")
	}
}

func writeJSON(
	w http.ResponseWriter,
	status int,
	data interface{},
) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	_ = json.NewEncoder(w).Encode(data)
}

func writeError(
	w http.ResponseWriter,
	status int,
	message string,
) {
	writeJSON(w, status, map[string]string{
		"error": strings.TrimSpace(message),
	})
}
