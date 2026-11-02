package executor

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type mockDeploymentGetter struct {
	getByIDFunc func(ctx context.Context, id uuid.UUID) (model.Deployment, error)
}

func (m *mockDeploymentGetter) GetByID(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
	if m.getByIDFunc != nil {
		return m.getByIDFunc(ctx, id)
	}
	return model.Deployment{}, nil
}

func TestKubernetesExecutorSuccessfulRollout(t *testing.T) {
	deploymentID := uuid.New()
	projectID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    projectID,
				Environment:  "staging",
				Image:        "ghcr.io/cloudforge/api:v1.2.0",
				GitCommitSHA: "abc1234567",
				Namespace:    "staging-ns",
			}, nil
		},
	}

	commandsRun := make([]string, 0)
	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		cmdStr := name + " " + strings.Join(args, " ")
		commandsRun = append(commandsRun, cmdStr)

		if len(args) > 0 && args[0] == "apply" {
			if !strings.Contains(string(stdin), "ghcr.io/cloudforge/api:v1.2.0") {
				t.Errorf("expected manifest to contain image, got: %s", string(stdin))
			}
			return []byte("deployment.apps/app-" + projectID.String()[:8] + " created"), nil
		}

		if len(args) > 0 && args[0] == "rollout" {
			return []byte("deployment \"app-" + projectID.String()[:8] + "\" successfully rolled out"), nil
		}

		return nil, nil
	}

	exec := NewKubernetesExecutorWithRunner(getter, "kubectl", 30*time.Second, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}

	if result.Status != "succeeded" {
		t.Fatalf("expected succeeded, got %s", result.Status)
	}

	if len(commandsRun) != 2 {
		t.Fatalf("expected 2 kubectl commands, got %d", len(commandsRun))
	}
}

func TestKubernetesExecutorApplyFails(t *testing.T) {
	deploymentID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "nginx:latest",
				GitCommitSHA: "c0ffee1234",
				Namespace:    "prod",
			}, nil
		},
	}

	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		return []byte("Error from server (NotFound): namespaces \"prod\" not found"), errors.New("exit status 1")
	}

	exec := NewKubernetesExecutorWithRunner(getter, "kubectl", 10*time.Second, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err == nil {
		t.Fatal("expected apply error, got nil")
	}

	if result.Status != "failed" {
		t.Fatalf("expected status failed, got %s", result.Status)
	}

	if !strings.Contains(result.Message, "namespaces \"prod\" not found") {
		t.Fatalf("expected error message to contain namespace error, got: %s", result.Message)
	}
}

func TestKubernetesExecutorRolloutFails(t *testing.T) {
	deploymentID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "broken-image:v9.9.9",
				GitCommitSHA: "deadbeef1234",
				Namespace:    "prod",
			}, nil
		},
	}

	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		if len(args) > 0 && args[0] == "apply" {
			return []byte("deployment.apps configured"), nil
		}
		return []byte("error: deployment \"app\" exceeded its progress deadline: CrashLoopBackOff"), errors.New("exit status 1")
	}

	exec := NewKubernetesExecutorWithRunner(getter, "kubectl", 10*time.Second, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err == nil {
		t.Fatal("expected rollout error, got nil")
	}

	if result.Status != "failed" {
		t.Fatalf("expected status failed, got %s", result.Status)
	}

	if !strings.Contains(result.Message, "CrashLoopBackOff") {
		t.Fatalf("expected error message to contain CrashLoopBackOff, got: %s", result.Message)
	}
}

func TestKubernetesExecutorRolloutTimeout(t *testing.T) {
	deploymentID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    uuid.New(),
				Environment:  "development",
				Image:        "test:v1",
				GitCommitSHA: "abcdef1234",
				Namespace:    "dev",
			}, nil
		},
	}

	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		if len(args) > 0 && args[0] == "apply" {
			return []byte("applied"), nil
		}
		return []byte("error: timed out waiting for the condition"), errors.New("timeout")
	}

	exec := NewKubernetesExecutorWithRunner(getter, "kubectl", 5*time.Second, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}

	if result.Status != "failed" {
		t.Fatalf("expected failed status, got %s", result.Status)
	}

	if !strings.Contains(result.Message, "timed out") {
		t.Fatalf("expected timeout in error message, got: %s", result.Message)
	}
}

func TestKubernetesExecutorRejectsNilID(t *testing.T) {
	exec := NewKubernetesExecutor(&mockDeploymentGetter{})
	_, err := exec.Execute(context.Background(), uuid.Nil)
	if err == nil {
		t.Fatal("expected error for nil UUID, got nil")
	}
}

func TestKubernetesExecutorDeploymentNotFound(t *testing.T) {
	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{}, errors.New("deployment not found")
		},
	}

	exec := NewKubernetesExecutor(getter)
	_, err := exec.Execute(context.Background(), uuid.New())
	if err == nil {
		t.Fatal("expected error when deployment is not found, got nil")
	}
}
