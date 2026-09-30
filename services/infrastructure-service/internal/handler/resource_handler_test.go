package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/service"
)

type mockResourceManager struct {
	resource      model.InfrastructureResource
	listLimit     int
	listOffset    int
	listCallCount int
}

func (m *mockResourceManager) Create(
	ctx context.Context,
	input model.CreateResourceInput,
) (model.InfrastructureResource, error) {
	m.resource = model.InfrastructureResource{
		ID:       uuid.New(),
		Name:     input.Name,
		Provider: input.Provider,
		Region:   input.Region,
		Status:   model.ResourceStatusActive,
	}

	return m.resource, nil
}

func (m *mockResourceManager) GetByID(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	if id != m.resource.ID {
		return model.InfrastructureResource{}, repository.ErrResourceNotFound
	}

	return m.resource, nil
}

func (m *mockResourceManager) List(
	ctx context.Context,
	limit int,
	offset int,
) ([]model.InfrastructureResource, error) {
	m.listLimit = limit
	m.listOffset = offset
	m.listCallCount++

	return []model.InfrastructureResource{m.resource}, nil
}

func (m *mockResourceManager) Update(
	ctx context.Context,
	id uuid.UUID,
	input model.UpdateResourceInput,
) (model.InfrastructureResource, error) {
	return m.resource, nil
}

func (m *mockResourceManager) Delete(
	ctx context.Context,
	id uuid.UUID,
) error {
	if id != m.resource.ID {
		return repository.ErrResourceNotFound
	}

	return nil
}

type mockProvisioningManager struct {
	resource       model.InfrastructureResource
	planCallCount  int
	applyCallCount int
	lastPlanID     uuid.UUID
	lastApplyID    uuid.UUID
	lastPlanHash   string
	planError      error
	applyError     error
}

func (m *mockProvisioningManager) Plan(
	ctx context.Context,
	id uuid.UUID,
) (model.InfrastructureResource, error) {
	m.planCallCount++
	m.lastPlanID = id

	if m.planError != nil {
		return model.InfrastructureResource{}, m.planError
	}

	return m.resource, nil
}

func (m *mockProvisioningManager) Apply(
	ctx context.Context,
	id uuid.UUID,
	planHash string,
) (model.InfrastructureResource, error) {
	m.applyCallCount++
	m.lastApplyID = id
	m.lastPlanHash = planHash

	if m.applyError != nil {
		return model.InfrastructureResource{}, m.applyError
	}

	return m.resource, nil
}

func newTestHandler(
	manager *mockResourceManager,
	provisioning *mockProvisioningManager,
) *ResourceHandler {
	return NewResourceHandler(manager, provisioning)
}

func TestHealthHandler(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()

	handler.Health(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	var response map[string]string

	if err := json.NewDecoder(recorder.Body).Decode(&response); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if response["status"] != "ok" {
		t.Fatalf("expected status ok, got %s", response["status"])
	}
}

func TestCreateHandler(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	body := `{
		"name": "Production VPC",
		"description": "Production network",
		"provider": "aws",
		"region": "eu-west-1",
		"environment": "production",
		"terraform_directory": "terraform/aws/vpc"
	}`

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources",
		strings.NewReader(body),
	)
	recorder := httptest.NewRecorder()

	handler.Create(recorder, request)

	if recorder.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", recorder.Code)
	}

	if manager.resource.Name != "Production VPC" {
		t.Fatalf("unexpected resource name: %s", manager.resource.Name)
	}
}

func TestCreateHandlerInvalidJSON(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources",
		strings.NewReader(`{"name":`),
	)
	recorder := httptest.NewRecorder()

	handler.Create(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}
}

func TestGetByIDHandlerInvalidUUID(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources/invalid-id",
		nil,
	)

	request.SetPathValue("id", "invalid-id")

	recorder := httptest.NewRecorder()

	handler.GetByID(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}
}

func TestListHandlerDefaultPagination(t *testing.T) {
	manager := &mockResourceManager{
		resource: model.InfrastructureResource{
			ID:       uuid.New(),
			Name:     "Production VPC",
			Provider: model.ProviderAWS,
		},
	}

	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	if manager.listCallCount != 1 {
		t.Fatalf("expected one list call, got %d", manager.listCallCount)
	}

	if manager.listLimit != 20 {
		t.Fatalf("expected default limit 20, got %d", manager.listLimit)
	}

	if manager.listOffset != 0 {
		t.Fatalf("expected default offset 0, got %d", manager.listOffset)
	}
}

func TestListHandlerValidPagination(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=10&offset=5",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	if manager.listLimit != 10 {
		t.Fatalf("expected limit 10, got %d", manager.listLimit)
	}

	if manager.listOffset != 5 {
		t.Fatalf("expected offset 5, got %d", manager.listOffset)
	}
}

func TestListHandlerInvalidLimit(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=abc",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid limit")
	}
}

func TestListHandlerLimitBelowMinimum(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=0",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid limit")
	}
}

func TestListHandlerLimitAboveMaximum(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?limit=101",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid limit")
	}
}

func TestListHandlerInvalidOffset(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?offset=abc",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid offset")
	}
}

func TestListHandlerNegativeOffset(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/resources?offset=-1",
		nil,
	)

	recorder := httptest.NewRecorder()

	handler.List(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if manager.listCallCount != 0 {
		t.Fatal("service should not be called for invalid offset")
	}
}

func TestDeleteHandlerNotFound(t *testing.T) {
	manager := &mockResourceManager{
		resource: model.InfrastructureResource{
			ID: uuid.New(),
		},
	}

	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	unknownID := uuid.New().String()

	request := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/resources/"+unknownID,
		nil,
	)

	request.SetPathValue("id", unknownID)

	recorder := httptest.NewRecorder()

	handler.Delete(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", recorder.Code)
	}
}

func TestDeleteHandlerInvalidUUID(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/resources/invalid-id",
		nil,
	)

	request.SetPathValue("id", "invalid-id")

	recorder := httptest.NewRecorder()

	handler.Delete(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}
}

func TestPlanHandlerSuccess(t *testing.T) {
	id := uuid.New()

	manager := &mockResourceManager{}

	provisioning := &mockProvisioningManager{
		resource: model.InfrastructureResource{
			ID:     id,
			Name:   "Production VPC",
			Status: model.ResourceStatusAwaitingApproval,
		},
	}

	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/plan",
		nil,
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Plan(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	if provisioning.planCallCount != 1 {
		t.Fatalf(
			"expected one plan call, got %d",
			provisioning.planCallCount,
		)
	}

	if provisioning.lastPlanID != id {
		t.Fatalf(
			"expected plan ID %s, got %s",
			id,
			provisioning.lastPlanID,
		)
	}
}

func TestPlanHandlerInvalidUUID(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/invalid-id/plan",
		nil,
	)

	request.SetPathValue("id", "invalid-id")

	recorder := httptest.NewRecorder()

	handler.Plan(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if provisioning.planCallCount != 0 {
		t.Fatal("provisioning service should not be called")
	}
}

func TestPlanHandlerNotFound(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{
		planError: repository.ErrResourceNotFound,
	}

	handler := newTestHandler(manager, provisioning)

	id := uuid.New()

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/plan",
		nil,
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Plan(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", recorder.Code)
	}
}

func TestPlanHandlerConflict(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{
		planError: service.ErrInvalidProvisioningState,
	}

	handler := newTestHandler(manager, provisioning)

	id := uuid.New()

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/plan",
		nil,
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Plan(recorder, request)

	if recorder.Code != http.StatusConflict {
		t.Fatalf("expected status 409, got %d", recorder.Code)
	}
}

func TestPlanHandlerInternalError(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{
		planError: errors.New("terraform plan failed"),
	}

	handler := newTestHandler(manager, provisioning)

	id := uuid.New()

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/plan",
		nil,
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Plan(recorder, request)

	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf(
			"expected status 500, got %d",
			recorder.Code,
		)
	}
}

func TestApplyHandlerSuccess(t *testing.T) {
	id := uuid.New()
	planHash := "abcdef123456"

	manager := &mockResourceManager{}

	provisioning := &mockProvisioningManager{
		resource: model.InfrastructureResource{
			ID:     id,
			Name:   "Production VPC",
			Status: model.ResourceStatusActive,
		},
	}

	handler := newTestHandler(manager, provisioning)

	body := `{"plan_hash":"` + planHash + `"}`

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/apply",
		strings.NewReader(body),
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Apply(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	if provisioning.applyCallCount != 1 {
		t.Fatalf(
			"expected one apply call, got %d",
			provisioning.applyCallCount,
		)
	}

	if provisioning.lastApplyID != id {
		t.Fatalf(
			"expected apply ID %s, got %s",
			id,
			provisioning.lastApplyID,
		)
	}

	if provisioning.lastPlanHash != planHash {
		t.Fatalf(
			"expected plan hash %s, got %s",
			planHash,
			provisioning.lastPlanHash,
		)
	}
}

func TestApplyHandlerInvalidUUID(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/invalid-id/apply",
		strings.NewReader(`{"plan_hash":"abc"}`),
	)

	request.SetPathValue("id", "invalid-id")

	recorder := httptest.NewRecorder()

	handler.Apply(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if provisioning.applyCallCount != 0 {
		t.Fatal("provisioning service should not be called")
	}
}

func TestApplyHandlerInvalidJSON(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{}
	handler := newTestHandler(manager, provisioning)

	id := uuid.New()

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/apply",
		strings.NewReader(`{"plan_hash":`),
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Apply(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", recorder.Code)
	}

	if provisioning.applyCallCount != 0 {
		t.Fatal("provisioning service should not be called")
	}
}

func TestApplyHandlerNotFound(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{
		applyError: repository.ErrResourceNotFound,
	}

	handler := newTestHandler(manager, provisioning)

	id := uuid.New()

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/apply",
		strings.NewReader(`{"plan_hash":"abc"}`),
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Apply(recorder, request)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", recorder.Code)
	}
}

func TestApplyHandlerConflictErrors(t *testing.T) {
	conflictErrors := []error{
		service.ErrInvalidProvisioningState,
		service.ErrApprovalExpired,
		service.ErrPlanHashMismatch,
	}

	for _, testErr := range conflictErrors {
		t.Run(testErr.Error(), func(t *testing.T) {
			manager := &mockResourceManager{}
			provisioning := &mockProvisioningManager{
				applyError: testErr,
			}

			handler := newTestHandler(manager, provisioning)

			id := uuid.New()

			request := httptest.NewRequest(
				http.MethodPost,
				"/api/v1/resources/"+id.String()+"/apply",
				strings.NewReader(`{"plan_hash":"abc"}`),
			)

			request.SetPathValue("id", id.String())

			recorder := httptest.NewRecorder()

			handler.Apply(recorder, request)

			if recorder.Code != http.StatusConflict {
				t.Fatalf(
					"expected status 409, got %d",
					recorder.Code,
				)
			}
		})
	}
}

func TestApplyHandlerInternalError(t *testing.T) {
	manager := &mockResourceManager{}
	provisioning := &mockProvisioningManager{
		applyError: errors.New("terraform apply failed"),
	}

	handler := newTestHandler(manager, provisioning)

	id := uuid.New()

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/resources/"+id.String()+"/apply",
		strings.NewReader(`{"plan_hash":"abc"}`),
	)

	request.SetPathValue("id", id.String())

	recorder := httptest.NewRecorder()

	handler.Apply(recorder, request)

	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf(
			"expected status 500, got %d",
			recorder.Code,
		)
	}
}
