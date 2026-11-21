package service

import (
	"context"
	"errors"
	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestProgressiveCreationIsOptInAndRequesterIsVerified(t *testing.T) {
	project := uuid.New()
	input := model.CreateDeploymentInput{ProjectID: project, Environment: "staging", Image: "ghcr.io/example/app@sha256:" + strings.Repeat("a", 64), GitCommitSHA: "abcdef1", Namespace: "cf-" + project.String(), Strategy: model.DeploymentStrategy{Type: "blue-green"}}
	store := &mockDeploymentStore{}
	service := NewDeploymentService(store)
	req := identity.WithClaims(httptest.NewRequest("POST", "/", nil), identity.Claims{Issuer: "frontend", Subject: "requester", Role: "platform-engineer"})
	if _, err := service.Create(req.Context(), input); !errors.Is(err, ErrProgressiveUnavailable) {
		t.Fatal(err)
	}
	service.SetProgressiveEnabled(true)
	got, err := service.Create(req.Context(), input)
	if err != nil || got.CreatedBy != "requester" || got.Strategy.Type != "blue-green" {
		t.Fatal(got, err)
	}
	if _, err := service.Create(context.Background(), input); !errors.Is(err, ErrProgressiveUnavailable) {
		t.Fatal("unverified requester", err)
	}
	input.Image = "nginx:latest"
	if _, err := service.Create(req.Context(), input); !errors.Is(err, ErrInvalidImage) {
		t.Fatal("mutable progressive image accepted", err)
	}
}
func TestProgressiveRevisionCannotBeMutatedAfterApprovalBinding(t *testing.T) {
	d := model.Deployment{ID: uuid.New(), Strategy: model.DeploymentStrategy{Type: "blue-green"}}
	store := &mockDeploymentStore{getByIDFunc: func(context.Context, uuid.UUID) (model.Deployment, error) { return d, nil }}
	value := "changed-image"
	_, err := NewDeploymentService(store).Update(context.Background(), d.ID, model.UpdateDeploymentInput{Image: &value})
	if !errors.Is(err, repository.ErrDeploymentConflict) {
		t.Fatal(err)
	}
}
