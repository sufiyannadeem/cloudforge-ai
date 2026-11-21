package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"

	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type ResourceHandler struct {
	TerraformReadOnly   bool
	DriftStore          *repository.ResourceRepository
	DriftRunner         *terraform.Runner
	resourceManager     service.ResourceManager
	provisioningManager service.ProvisioningManager
}

func NewResourceHandler(
	resourceManager service.ResourceManager,
	provisioningManager service.ProvisioningManager,
) *ResourceHandler {
	return &ResourceHandler{
		resourceManager:     resourceManager,
		provisioningManager: provisioningManager,
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

	if identity.FromContext(r.Context()).Role == "developer" {
		projectID, err := uuid.Parse(strings.TrimSpace(input.ProjectID))
		if err != nil || projectID == uuid.Nil {
			writeError(w, http.StatusNotFound, "project not found")
			return
		}
		if err := identity.RequireProjectWrite(r.Context(), projectID.String()); err != nil {
			writeError(w, identity.AccessStatus(err), "project access denied")
			return
		}
		input.TerraformDirectory = ""
	}
	resource, err := h.resourceManager.Create(r.Context(), input)
	if err != nil {
		writeError(w, http.StatusBadRequest, safeResourceError(r, err))
		return
	}

	writeJSON(w, http.StatusCreated, publicResource(resource))
}

func (h *ResourceHandler) List(w http.ResponseWriter, r *http.Request) {
	limit, err := parsePaginationValue(r, "limit", 20, 1, 100)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	offset, err := parsePaginationValue(r, "offset", 0, 0, 1000000)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	ctx := r.Context()
	if filter := r.URL.Query().Get("review_status"); filter != "" {
		if filter != "submitted" {
			writeError(w, http.StatusBadRequest, "invalid review status filter")
			return
		}
		if identity.FromContext(ctx).Role != "platform-engineer" {
			writeError(w, http.StatusForbidden, "review queue permission denied")
			return
		}
		ctx = repository.WithPendingReviews(ctx)
	}

	resources, err := h.resourceManager.List(
		ctx,
		limit,
		offset,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, safeResourceError(r, err))
		return
	}

	if resources == nil {
		resources = []model.InfrastructureResource{}
	}
	for i := range resources {
		resources[i] = publicResource(resources[i])
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

		writeError(w, http.StatusInternalServerError, safeResourceError(r, err))
		return
	}

	writeJSON(w, http.StatusOK, publicResource(resource))
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

	writeJSON(w, http.StatusOK, publicResource(resource))
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

		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (h *ResourceHandler) Plan(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	resource, err := h.provisioningManager.Plan(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrResourceNotFound) {
			writeError(w, http.StatusNotFound, "resource not found")
			return
		}

		if errors.Is(err, service.ErrInvalidProvisioningState) {
			writeProvisioningError(w, err)
			return
		}

		writeError(w, http.StatusInternalServerError, "Terraform plan failed")
		return
	}

	writeJSON(w, http.StatusOK, publicResource(resource))
}

func (h *ResourceHandler) GetPlan(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	planDetails, err := h.provisioningManager.GetPlan(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrResourceNotFound) {
			writeError(w, http.StatusNotFound, "resource not found")
			return
		}

		writeError(w, http.StatusNotFound, "saved plan unavailable")
		return
	}

	planDetails.Configuration = map[string]any{}
	planDetails.PlanSummary = terraform.PublicPlanSummary(planDetails.PlanSummary)
	writeJSON(w, http.StatusOK, planDetails)
}

func (h *ResourceHandler) Apply(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var input model.ApplyResourceInput

	if err := decodeJSON(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	actor := identity.FromContext(r.Context()).Subject
	log.Printf("terraform_apply_requested actor=%q resource_id=%q", actor, id.String())
	resource, err := h.provisioningManager.Apply(
		r.Context(),
		id,
		input.PlanHash,
	)
	if err != nil {
		if errors.Is(err, repository.ErrResourceNotFound) {
			writeError(w, http.StatusNotFound, "resource not found")
			return
		}

		if errors.Is(err, service.ErrInvalidProvisioningState) ||
			errors.Is(err, service.ErrApprovalExpired) ||
			errors.Is(err, service.ErrPlanHashMismatch) || errors.Is(err, repository.ErrResourceConflict) {
			writeProvisioningError(w, err)
			return
		}

		writeError(w, http.StatusInternalServerError, "Terraform operation failed")
		return
	}

	writeJSON(w, http.StatusOK, publicResource(resource))
}

// PlanDestroy handles POST /api/v1/resources/{id}/destroy/plan.
func (h *ResourceHandler) PlanDestroy(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	resource, err := h.provisioningManager.PlanDestroy(r.Context(), id)
	if err != nil {
		writeProvisioningError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, publicResource(resource))
}

// ApplyDestroy handles POST /api/v1/resources/{id}/destroy/apply. The body
// must carry the plan_hash the human reviewed.
func (h *ResourceHandler) ApplyDestroy(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var input model.ApplyResourceInput

	if err := decodeJSON(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	actor := identity.FromContext(r.Context()).Subject
	log.Printf("terraform_destroy_apply_requested actor=%q resource_id=%q", actor, id.String())
	resource, err := h.provisioningManager.ApplyDestroy(
		r.Context(),
		id,
		input.PlanHash,
	)
	if err != nil {
		writeProvisioningError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, publicResource(resource))
}

func publicResource(resource model.InfrastructureResource) model.InfrastructureResource {
	resource.Configuration = map[string]any{}
	resource.PlanPath = ""
	resource.DestroyPlanPath = ""
	resource.TerraformDirectory = ""
	resource.PlanSummary = terraform.PublicPlanSummary(resource.PlanSummary)
	return resource
}

func (h *ResourceHandler) Review(w http.ResponseWriter, r *http.Request) {
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, http.StatusNotFound, "resource not found")
		return
	}
	var input model.PlanReviewInput
	if err := decodeJSON(r, &input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid plan review")
		return
	}
	if err := h.provisioningManager.Review(r.Context(), id, input); err != nil {
		writeProvisioningError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func safeResourceError(r *http.Request, err error) string {
	if identity.FromContext(r.Context()).Role == "developer" {
		return "infrastructure operation failed"
	}
	return err.Error()
}

func writeProvisioningError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, repository.ErrResourceNotFound):
		writeError(w, http.StatusNotFound, "resource not found")
	case errors.Is(err, repository.ErrReviewForbidden):
		writeError(w, http.StatusForbidden, "requesters cannot decide their own plan")
	case errors.Is(err, service.ErrReviewDenied):
		writeError(w, http.StatusForbidden, "plan review permission denied")
	case errors.Is(err, service.ErrApprovalExpired):
		writeError(w, http.StatusConflict, "terraform plan approval has expired")
	case errors.Is(err, service.ErrPlanHashMismatch):
		writeError(w, http.StatusConflict, "terraform plan hash mismatch")
	case errors.Is(err, repository.ErrResourceConflict):
		writeError(w, http.StatusConflict, "approval is missing, stale, or already used")
	case errors.Is(err, service.ErrInvalidProvisioningState):
		writeError(w, http.StatusConflict, "resource is not ready for this operation")
	default:
		writeError(w, http.StatusInternalServerError, "Terraform operation failed")
	}
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

	var extra interface{}

	if err := decoder.Decode(&extra); err == nil {
		return errors.New("request body must contain a single JSON object")
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

func parsePaginationValue(
	r *http.Request,
	key string,
	defaultValue int,
	minimum int,
	maximum int,
) (int, error) {
	value := r.URL.Query().Get(key)

	if value == "" {
		return defaultValue, nil
	}

	parsedValue, err := strconv.Atoi(value)
	if err != nil {
		return 0, fmt.Errorf("%s must be a valid integer", key)
	}

	if parsedValue < minimum || parsedValue > maximum {
		return 0, fmt.Errorf(
			"%s must be between %d and %d",
			key,
			minimum,
			maximum,
		)
	}

	return parsedValue, nil
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
