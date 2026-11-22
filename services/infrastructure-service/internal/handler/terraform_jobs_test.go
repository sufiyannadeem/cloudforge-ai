package handler

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type fixtureJobs struct {
	job    repository.TerraformJob
	code   int
	result []byte
}

func (f *fixtureJobs) EnqueueTerraformJob(_ context.Context, j repository.TerraformJob) error {
	f.job = j
	return nil
}
func (f *fixtureJobs) GetTerraformJob(_ context.Context, r, id uuid.UUID) (repository.TerraformJob, error) {
	if r != f.job.ResourceID || id != f.job.ID {
		return repository.TerraformJob{}, pgx.ErrNoRows
	}
	return f.job, nil
}
func (f *fixtureJobs) ClaimTerraformJob(context.Context) (repository.TerraformJob, error) {
	return f.job, nil
}
func (f *fixtureJobs) FinishTerraformJob(_ context.Context, _ uuid.UUID, code int, b []byte) error {
	f.code = code
	f.result = b
	return nil
}

func TestTerraformIntakeReturnsReceiptBeforeExecutionAndPollIsScoped(t *testing.T) {
	id := uuid.New()
	p := &mockProvisioningManager{resource: model.InfrastructureResource{ID: id}}
	h := NewResourceHandler(&mockResourceManager{resource: model.InfrastructureResource{ID: id}}, p)
	jobs := &fixtureJobs{}
	h.Jobs = jobs
	path := "/api/v1/resources/" + id.String() + "/plan"
	req := identity.WithClaims(httptest.NewRequest("POST", path, strings.NewReader("")), identity.Claims{Issuer: "frontend", Subject: "operator", Role: "platform-engineer"})
	rec := httptest.NewRecorder()
	newResourceMux(h).ServeHTTP(rec, req)
	if rec.Code != 202 || p.planCallCount != 0 {
		t.Fatalf("intake executed synchronously: %d", rec.Code)
	}
	var receipt repository.TerraformJob
	if err := json.Unmarshal(rec.Body.Bytes(), &receipt); err != nil || receipt.ID == uuid.Nil {
		t.Fatal("receipt missing")
	}
	poll := httptest.NewRecorder()
	newResourceMux(h).ServeHTTP(poll, httptest.NewRequest("GET", path[:len(path)-5]+"/jobs/"+receipt.ID.String(), nil))
	if poll.Code != 200 {
		t.Fatalf("poll: %d", poll.Code)
	}
	other := httptest.NewRecorder()
	newResourceMux(h).ServeHTTP(other, httptest.NewRequest("GET", "/api/v1/resources/"+uuid.NewString()+"/jobs/"+receipt.ID.String(), nil))
	if other.Code != 404 {
		t.Fatal("cross-resource receipt leaked")
	}
	h.executeTerraformJob(context.Background(), identity.ProjectAccess{}, jobs.job)
	if p.planCallCount != 1 || jobs.code != 200 {
		t.Fatalf("worker failed: calls=%d status=%d body=%s", p.planCallCount, jobs.code, jobs.result)
	}
}

func TestTerraformWorkerRejectsUnprivilegedMutation(t *testing.T) {
	p := &mockProvisioningManager{}
	jobs := &fixtureJobs{}
	h := NewResourceHandler(&mockResourceManager{}, p)
	h.Jobs = jobs
	h.executeTerraformJob(context.Background(), identity.ProjectAccess{}, repository.TerraformJob{ID: uuid.New(), ResourceID: uuid.New(), Path: "/api/v1/resources/" + uuid.NewString() + "/apply", Claims: identity.Claims{Role: "sre"}})
	if jobs.code != 403 || p.applyCallCount != 0 {
		t.Fatal("worker bypassed authorization")
	}
}
