package handler

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/repository"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type TerraformJobStore interface {
	EnqueueTerraformJob(context.Context, repository.TerraformJob) error
	GetTerraformJob(context.Context, uuid.UUID, uuid.UUID) (repository.TerraformJob, error)
	ClaimTerraformJob(context.Context) (repository.TerraformJob, error)
	FinishTerraformJob(context.Context, uuid.UUID, int, []byte) error
}

func (h *ResourceHandler) asyncTerraform(next http.HandlerFunc) http.HandlerFunc {
	if h.Jobs == nil {
		return next
	} // Only unit fixtures use synchronous handlers.
	return func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		r = r.WithContext(ctx)
		id, err := parseResourceID(r)
		if err != nil {
			writeError(w, 400, "invalid resource ID")
			return
		}
		if _, err = h.resourceManager.GetByID(r.Context(), id); err != nil {
			writeError(w, 404, "resource not found")
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 65536))
		if err != nil {
			writeError(w, 400, "invalid operation body")
			return
		}
		if body == nil {
			body = []byte{}
		}
		job := repository.TerraformJob{ID: uuid.New(), ResourceID: id, Path: r.URL.Path, Body: body, Claims: identity.FromContext(r.Context()), Status: "queued"}
		if err = h.Jobs.EnqueueTerraformJob(r.Context(), job); err != nil {
			writeError(w, 409, "operation already queued or job storage unavailable")
			return
		}
		writeJSON(w, http.StatusAccepted, job)
	}
}

func (h *ResourceHandler) JobStatus(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	r = r.WithContext(ctx)
	id, err := parseResourceID(r)
	if err != nil {
		writeError(w, 400, "invalid resource ID")
		return
	}
	jobID, err := uuid.Parse(r.PathValue("job"))
	if err != nil {
		writeError(w, 400, "invalid job ID")
		return
	}
	if h.Jobs == nil {
		writeError(w, 503, "job storage unavailable")
		return
	}
	j, err := h.Jobs.GetTerraformJob(r.Context(), id, jobID)
	if err != nil {
		writeError(w, 404, "job not found")
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, 200, j)
}

// One worker per replica. PostgreSQL claims work once; service leases and fenced
// state writes remain authoritative. SIGTERM cancels the runner/process group.
func (h *ResourceHandler) RunTerraformJobs(ctx context.Context, access identity.ProjectAccess) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
		if h.TerraformReadOnly {
			continue
		}
		j, err := h.Jobs.ClaimTerraformJob(ctx)
		if errors.Is(err, pgx.ErrNoRows) {
			continue
		}
		if err != nil {
			log.Print("Terraform job claim unavailable")
			continue
		}
		h.executeTerraformJob(ctx, access, j)
	}
}

func (h *ResourceHandler) executeTerraformJob(ctx context.Context, access identity.ProjectAccess, j repository.TerraformJob) {
	execCtx, cancel := context.WithTimeout(ctx, 35*time.Minute)
	defer cancel()
	r := httptest.NewRequest(http.MethodPost, j.Path, bytes.NewReader(j.Body)).WithContext(execCtx)
	r = access.Attach(identity.WithClaims(r, j.Claims))
	// Recheck developer membership after waiting in the queue. Approval hash,
	// revision, expiry and caller are checked again by the provisioning service.
	recorder := httptest.NewRecorder()
	if j.Claims.Role == "developer" {
		if err := access.Resource(r.Context(), "infrastructure", j.ResourceID.String(), true); err != nil {
			writeError(recorder, 403, "resource access denied")
		} else {
			newResourceMuxForWorker(h).ServeHTTP(recorder, r)
		}
	} else if j.Claims.Role == "platform-engineer" {
		newResourceMuxForWorker(h).ServeHTTP(recorder, r)
	} else {
		writeError(recorder, 403, "operation permission denied")
	}
	saveCtx, stop := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer stop()
	if err := h.Jobs.FinishTerraformJob(saveCtx, j.ID, recorder.Code, recorder.Body.Bytes()); err != nil {
		log.Print("Terraform job completion requires reconciliation")
	}
}

func newResourceMuxForWorker(h *ResourceHandler) http.Handler {
	// Copy disables intake wrapping, while retaining the same approvals/leases.
	worker := *h
	worker.Jobs = nil
	return newResourceMux(&worker)
}
