package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/service"
)

type ResourceHandler struct {
	resourceManager service.ResourceManager
}

func NewResourceHandler(
	resourceManager service.ResourceManager,
) *ResourceHandler {
	return &ResourceHandler{
		resourceManager: resourceManager,
	}
}

func (h *ResourceHandler) Health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"service": "infrastructure-service",
	})
}

func (h *ResourceHandler) Create(w http.ResponseWriter, r *http.Request) {
	var input model.CreateResourceInput

	if err := decodeJSON(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	resource, err := h.resourceManager.Create(r.Context(), input)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, resource)
}

func (h *ResourceHandler) List(w http.ResponseWriter, r *http.Request) {
	limit := parseQueryInt(r, "limit", 20)
	offset := parseQueryInt(r, "offset", 0)

	resources, err := h.resourceManager.List(
		r.Context(),
		limit,
		offset,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"items":  resources,
		"limit":  limit,
		"offset": offset,
	})
}

func (h *ResourceHandler) GetByID(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	resource, err := h.resourceManager.GetByID(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrResourceNotFound) {
			writeError(w, http.StatusNotFound, "resource not found")
			return
		}

		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, resource)
}

func (h *ResourceHandler) Update(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var input model.UpdateResourceInput

	if err := decodeJSON(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	resource, err := h.resourceManager.Update(
		r.Context(),
		id,
		input,
	)
	if err != nil {
		if errors.Is(err, repository.ErrResourceNotFound) {
			writeError(w, http.StatusNotFound, "resource not found")
			return
		}

		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, resource)
}

func (h *ResourceHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	err = h.resourceManager.Delete(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrResourceNotFound) {
			writeError(w, http.StatusNotFound, "resource not found")
			return
		}

		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func decodeJSON(r *http.Request, destination interface{}) error {
	if r.Body == nil {
		return errors.New("request body cannot be empty")
	}

	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()

	if err := decoder.Decode(destination); err != nil {
		return errors.New("invalid JSON request body")
	}

	return nil
}

func parseResourceID(r *http.Request) (uuid.UUID, error) {
	id := strings.TrimSpace(r.PathValue("id"))

	if id == "" {
		return uuid.Nil, errors.New("resource ID is required")
	}

	parsedID, err := uuid.Parse(id)
	if err != nil {
		return uuid.Nil, errors.New("resource ID must be a valid UUID")
	}

	return parsedID, nil
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

	parsedValue, err := strconv.Atoi(value)
	if err != nil {
		return defaultValue
	}

	return parsedValue
}

func writeJSON(
	w http.ResponseWriter,
	statusCode int,
	value interface{},
) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)

	_ = json.NewEncoder(w).Encode(value)
}

func writeError(
	w http.ResponseWriter,
	statusCode int,
	message string,
) {
	writeJSON(w, statusCode, map[string]string{
		"error": message,
	})
}
