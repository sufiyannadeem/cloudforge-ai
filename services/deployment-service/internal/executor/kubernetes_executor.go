package executor

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

// DeploymentGetter provides access to deployment records for execution.
type DeploymentGetter interface {
	GetByID(ctx context.Context, id uuid.UUID) (model.Deployment, error)
}

// CommandRunner executes a command with stdin input and returns combined output.
type CommandRunner func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error)

func defaultCommandRunner(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	if len(stdin) > 0 {
		cmd.Stdin = bytes.NewReader(stdin)
	}

	output, err := cmd.CombinedOutput()
	return output, err
}

// KubernetesExecutor performs real workload delivery to Kubernetes / EKS clusters.
type KubernetesExecutor struct {
	deploymentGetter DeploymentGetter
	kubectlPath      string
	timeout          time.Duration
	runner           CommandRunner
}

// NewKubernetesExecutor creates a new executor with the default kubectl runner.
func NewKubernetesExecutor(getter DeploymentGetter) *KubernetesExecutor {
	return NewKubernetesExecutorWithRunner(getter, "kubectl", 120*time.Second, defaultCommandRunner)
}

// NewKubernetesExecutorWithRunner creates a new executor with a custom command runner.
func NewKubernetesExecutorWithRunner(
	getter DeploymentGetter,
	kubectlPath string,
	timeout time.Duration,
	runner CommandRunner,
) *KubernetesExecutor {
	if kubectlPath == "" {
		kubectlPath = "kubectl"
	}
	if timeout <= 0 {
		timeout = 120 * time.Second
	}
	if runner == nil {
		runner = defaultCommandRunner
	}

	return &KubernetesExecutor{
		deploymentGetter: getter,
		kubectlPath:      kubectlPath,
		timeout:          timeout,
		runner:           runner,
	}
}

// Execute deploys the container workload to Kubernetes and waits for rollout health.
func (k *KubernetesExecutor) Execute(
	ctx context.Context,
	deploymentID uuid.UUID,
) (Result, error) {
	start := time.Now()

	if deploymentID == uuid.Nil {
		return Result{}, errors.New("deployment ID is required")
	}

	if k.deploymentGetter == nil {
		return Result{}, errors.New("deployment getter is required")
	}

	deployment, err := k.deploymentGetter.GetByID(ctx, deploymentID)
	if err != nil {
		return Result{}, fmt.Errorf("retrieve deployment: %w", err)
	}

	workloadName := sanitizeWorkloadName(deployment)
	manifest := generateKubernetesManifest(deployment, workloadName)

	// Step 1: Apply workload manifest to cluster
	applyOutput, err := k.runner(
		ctx,
		[]byte(manifest),
		k.kubectlPath,
		"apply",
		"-f",
		"-",
		"-n",
		deployment.Namespace,
	)
	if err != nil {
		errMsg := strings.TrimSpace(string(applyOutput))
		if errMsg == "" {
			errMsg = err.Error()
		}

		return Result{
			DeploymentID: deploymentID,
			Status:       "failed",
			Message:      fmt.Sprintf("Kubernetes apply failed: %s", errMsg),
			Duration:     time.Since(start),
		}, fmt.Errorf("apply workload: %s", errMsg)
	}

	// Step 2: Track rollout status until ready or deadline exceeded
	timeoutStr := fmt.Sprintf("%ds", int(k.timeout.Seconds()))
	rolloutOutput, err := k.runner(
		ctx,
		nil,
		k.kubectlPath,
		"rollout",
		"status",
		fmt.Sprintf("deployment/%s", workloadName),
		"-n",
		deployment.Namespace,
		fmt.Sprintf("--timeout=%s", timeoutStr),
	)
	if err != nil {
		errMsg := strings.TrimSpace(string(rolloutOutput))
		if errMsg == "" {
			errMsg = err.Error()
		}

		return Result{
			DeploymentID: deploymentID,
			Status:       "failed",
			Message:      fmt.Sprintf("Rollout failed or timed out: %s", errMsg),
			Duration:     time.Since(start),
		}, fmt.Errorf("rollout status: %s", errMsg)
	}

	return Result{
		DeploymentID: deploymentID,
		Status:       "succeeded",
		Message:      fmt.Sprintf("Rollout succeeded for %s: pods ready and serving traffic", deployment.Image),
		Duration:     time.Since(start),
	}, nil
}

func sanitizeWorkloadName(d model.Deployment) string {
	idStr := d.ProjectID.String()
	if len(idStr) > 8 {
		idStr = idStr[:8]
	}
	return fmt.Sprintf("app-%s", idStr)
}

func generateKubernetesManifest(d model.Deployment, name string) string {
	return fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: %s
  namespace: %s
  labels:
    app.kubernetes.io/name: %s
    app.kubernetes.io/version: %s
    app.kubernetes.io/managed-by: cloudforge-ai
    cloudforge.ai/environment: %s
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: %s
  template:
    metadata:
      labels:
        app.kubernetes.io/name: %s
        app.kubernetes.io/version: %s
    spec:
      containers:
      - name: app
        image: %s
        ports:
        - containerPort: 8080
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 20
`, name, d.Namespace, name, d.GitCommitSHA, d.Environment, name, name, d.GitCommitSHA, d.Image)
}
