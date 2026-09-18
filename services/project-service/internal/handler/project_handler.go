package handler

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/service"
)

type ProjectHandler struct {
	projectService service.ProjectService
}

func NewProjectHandler(
	projectService service.ProjectService,
) *ProjectHandler {
	return &ProjectHandler{
		projectService: projectService,
	}
}

func (h *ProjectHandler) ServeHTTP(
	w http.ResponseWriter,
	r *http.Request,
) {
	switch {
	case r.URL.Path == "/projects" && r.Method == http.MethodPost:
		h.createProject(w, r)

	case r.URL.Path == "/projects" && r.Method == http.MethodGet:
		h.listProjects(w, r)

	case strings.HasPrefix(r.URL.Path, "/projects/"):
		h.handleProjectByID(w, r)

	default:
		writeError(
			w,
			http.StatusNotFound,
			"route not found",
		)
	}
}

func (h *ProjectHandler) handleProjectByID(
	w http.ResponseWriter,
	r *http.Request,
) {
	idText := strings.TrimPrefix(r.URL.Path, "/projects/")

	if idText == "" || strings.Contains(idText, "/") {
		writeError(
			w,
			http.StatusNotFound,
			"project route not found",
		)
		return
	}

	projectID, err := uuid.Parse(idText)
	if err != nil {
		writeError(
			w,
			http.StatusBadRequest,
			"invalid project ID",
		)
		return
	}

	switch r.Method {
	case http.MethodGet:
		h.getProject(w, r, projectID)

	case http.MethodPatch:
		h.updateProject(w, r, projectID)

	case http.MethodDelete:
		h.deleteProject(w, r, projectID)

	default:
		w.Header().Set("Allow", "GET, PATCH, DELETE")

		writeError(
			w,
			http.StatusMethodNotAllowed,
			"method not allowed",
		)
	}
}

func (h *ProjectHandler) createProject(
	w http.ResponseWriter,
	r *http.Request,
) {
	var input model.CreateProjectInput

	if err := decodeJSONBody(w, r, &input); err != nil {
		return
	}

	project, err := h.projectService.Create(
		r.Context(),
		input,
	)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	writeJSON(
		w,
		http.StatusCreated,
		project,
	)
}

func (h *ProjectHandler) listProjects(
	w http.ResponseWriter,
	r *http.Request,
) {
	limit, err := parseQueryInt(
		r,
		"limit",
		0,
	)
	if err != nil {
		writeError(
			w,
			http.StatusBadRequest,
			"invalid limit query parameter",
		)
		return
	}

	offset, err := parseQueryInt(
		r,
		"offset",
		0,
	)
	if err != nil {
		writeError(
			w,
			http.StatusBadRequest,
			"invalid offset query parameter",
		)
		return
	}

	projects, err := h.projectService.List(
		r.Context(),
		limit,
		offset,
	)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	// Reflect the service's default pagination limit.
	if limit == 0 {
		limit = service.DefaultPageLimit
	}

	writeJSON(
		w,
		http.StatusOK,
		map[string]interface{}{
			"data":   projects,
			"limit":  limit,
			"offset": offset,
			"count":  len(projects),
		},
	)
}

func (h *ProjectHandler) getProject(
	w http.ResponseWriter,
	r *http.Request,
	projectID uuid.UUID,
) {
	project, err := h.projectService.GetByID(
		r.Context(),
		projectID,
	)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	writeJSON(
		w,
		http.StatusOK,
		project,
	)
}

func (h *ProjectHandler) updateProject(
	w http.ResponseWriter,
	r *http.Request,
	projectID uuid.UUID,
) {
	var input model.UpdateProjectInput

	if err := decodeJSONBody(w, r, &input); err != nil {
		return
	}

	project, err := h.projectService.Update(
		r.Context(),
		projectID,
		input,
	)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	writeJSON(
		w,
		http.StatusOK,
		project,
	)
}

func (h *ProjectHandler) deleteProject(
	w http.ResponseWriter,
	r *http.Request,
	projectID uuid.UUID,
) {
	err := h.projectService.Delete(
		r.Context(),
		projectID,
	)
	if err != nil {
		handleServiceError(w, err)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func decodeJSONBody(
	w http.ResponseWriter,
	r *http.Request,
	destination interface{},
) error {
	if r.Body == nil {
		writeError(
			w,
			http.StatusBadRequest,
			"request body is required",
		)

		return errors.New("request body is required")
	}

	defer r.Body.Close()

	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()

	// Decode the first JSON value.
	if err := decoder.Decode(destination); err != nil {
		writeError(
			w,
			http.StatusBadRequest,
			"invalid JSON request body",
		)

		return err
	}

	// Ensure there is no second JSON value or trailing garbage.
	var extra interface{}

	if err := decoder.Decode(&extra); err != io.EOF {
		writeError(
			w,
			http.StatusBadRequest,
			"request body must contain one JSON object",
		)

		if err == nil {
			return errors.New("multiple JSON values in request body")
		}

		return errors.New("request body contains trailing data")
	}

	return nil
}

func parseQueryInt(
	r *http.Request,
	key string,
	defaultValue int,
) (int, error) {
	value := r.URL.Query().Get(key)

	if value == "" {
		return defaultValue, nil
	}

	parsedValue, err := strconv.Atoi(value)
	if err != nil {
		return 0, err
	}

	return parsedValue, nil
}

func handleServiceError(
	w http.ResponseWriter,
	err error,
) {
	switch {
	case errors.Is(err, service.ErrInvalidProjectName),
		errors.Is(err, service.ErrInvalidRepositoryURL),
		errors.Is(err, service.ErrInvalidDefaultBranch),
		errors.Is(err, service.ErrInvalidProjectStatus),
		errors.Is(err, service.ErrInvalidPagination):
		writeError(
			w,
			http.StatusBadRequest,
			err.Error(),
		)

	case errors.Is(err, repository.ErrProjectNotFound):
		writeError(
			w,
			http.StatusNotFound,
			"project not found",
		)

	default:
		log.Printf(
			"internal service error: %v",
			err,
		)

		writeError(
			w,
			http.StatusInternalServerError,
			"internal server error",
		)
	}
}

func writeJSON(
	w http.ResponseWriter,
	statusCode int,
	data interface{},
) {
	w.Header().Set(
		"Content-Type",
		"application/json",
	)

	w.WriteHeader(statusCode)

	if err := json.NewEncoder(w).Encode(data); err != nil {
		log.Printf(
			"failed to encode JSON response: %v",
			err,
		)
	}
}

func writeError(
	w http.ResponseWriter,
	statusCode int,
	message string,
) {
	writeJSON(
		w,
		statusCode,
		map[string]string{
			"error": message,
		},
	)
}
