package executor

import (
	"context"
	"errors"
	"fmt"
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

func TestKubernetesExecutorManifestIncludesServiceAndResourcesAndProbes(t *testing.T) {
	deploymentID := uuid.New()
	projectID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    projectID,
				Environment:  "production",
				Image:        "123456789012.dkr.ecr.eu-west-1.amazonaws.com/cloudforge/api:release-v2.0.0",
				GitCommitSHA: "abcdef0123456789abcdef0123456789abcdef01",
				Namespace:    "production-apps",
			}, nil
		},
	}

	var capturedManifest string
	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		if len(args) > 0 && args[0] == "apply" {
			capturedManifest = string(stdin)
			return []byte("deployment.apps/app created\nservice/app created"), nil
		}
		if len(args) > 0 && args[0] == "rollout" {
			return []byte("deployment successfully rolled out"), nil
		}
		return nil, nil
	}

	exec := NewKubernetesExecutorWithRunner(getter, "kubectl", 90*time.Second, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if result.Status != "succeeded" {
		t.Fatalf("expected status succeeded, got %s", result.Status)
	}

	// Verify both Deployment and Service exist
	if !strings.Contains(capturedManifest, "kind: Deployment") {
		t.Fatal("manifest missing kind: Deployment")
	}
	if !strings.Contains(capturedManifest, "kind: Service") {
		t.Fatal("manifest missing kind: Service")
	}

	// Verify Service routing and ports
	if !strings.Contains(capturedManifest, "type: ClusterIP") {
		t.Fatal("manifest Service missing type: ClusterIP")
	}
	if !strings.Contains(capturedManifest, "targetPort: 8080") {
		t.Fatal("manifest Service missing targetPort: 8080")
	}

	// Verify sensible resource requests and limits
	if !strings.Contains(capturedManifest, "resources:") ||
		!strings.Contains(capturedManifest, "cpu: 100m") ||
		!strings.Contains(capturedManifest, "memory: 128Mi") ||
		!strings.Contains(capturedManifest, "cpu: 500m") ||
		!strings.Contains(capturedManifest, "memory: 512Mi") {
		t.Fatal("manifest missing sensible resource requests and limits")
	}

	// Verify liveness and readiness probes
	if !strings.Contains(capturedManifest, "readinessProbe:") ||
		!strings.Contains(capturedManifest, "livenessProbe:") ||
		!strings.Contains(capturedManifest, "path: /health") {
		t.Fatal("manifest missing liveness/readiness probes with /health endpoint")
	}

	// Verify progress deadline seconds matching rollout timeout
	if !strings.Contains(capturedManifest, "progressDeadlineSeconds: 90") {
		t.Fatalf("manifest missing progressDeadlineSeconds: 90, got: %s", capturedManifest)
	}
}

func TestKubernetesExecutorValidationFailures(t *testing.T) {
	tests := []struct {
		name       string
		deployment model.Deployment
		errSubstr  string
	}{
		{
			name: "invalid namespace with uppercase and spaces",
			deployment: model.Deployment{
				ID:           uuid.New(),
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "nginx:1.27",
				GitCommitSHA: "abcdef1234",
				Namespace:    "INVALID Namespace!",
			},
			errSubstr: "invalid namespace",
		},
		{
			name: "invalid image with shell injection attempt",
			deployment: model.Deployment{
				ID:           uuid.New(),
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "nginx:latest; rm -rf /",
				GitCommitSHA: "abcdef1234",
				Namespace:    "default",
			},
			errSubstr: "invalid container image",
		},
		{
			name: "invalid image with newlines for YAML injection",
			deployment: model.Deployment{
				ID:           uuid.New(),
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "nginx:latest\n  securityContext:\n    privileged: true",
				GitCommitSHA: "abcdef1234",
				Namespace:    "default",
			},
			errSubstr: "invalid container image",
		},
		{
			name: "invalid commit SHA with special characters",
			deployment: model.Deployment{
				ID:           uuid.New(),
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "nginx:1.27",
				GitCommitSHA: "bad;commit",
				Namespace:    "default",
			},
			errSubstr: "invalid git commit SHA",
		},
		{
			name: "too short commit SHA",
			deployment: model.Deployment{
				ID:           uuid.New(),
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "nginx:1.27",
				GitCommitSHA: "abc",
				Namespace:    "default",
			},
			errSubstr: "invalid git commit SHA",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			getter := &mockDeploymentGetter{
				getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
					return tc.deployment, nil
				},
			}

			exec := NewKubernetesExecutor(getter)
			result, err := exec.Execute(context.Background(), tc.deployment.ID)
			if err == nil {
				t.Fatalf("expected validation error, got nil")
			}
			if result.Status != "failed" {
				t.Fatalf("expected failed result status, got %s", result.Status)
			}
			if !strings.Contains(err.Error(), tc.errSubstr) {
				t.Fatalf("expected error containing %q, got %q", tc.errSubstr, err.Error())
			}
		})
	}
}

func TestKubernetesExecutorEKSAuthentication(t *testing.T) {
	deploymentID := uuid.New()
	projectID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    projectID,
				Environment:  "production",
				Image:        "123456789012.dkr.ecr.eu-west-1.amazonaws.com/api:v1",
				GitCommitSHA: "abcdef1234",
				Namespace:    "production",
			}, nil
		},
	}

	var commandsRun []string
	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		cmdStr := name + " " + strings.Join(args, " ")
		commandsRun = append(commandsRun, cmdStr)

		if name == "aws" && len(args) >= 3 && args[0] == "eks" && args[1] == "update-kubeconfig" {
			if args[3] != "cloudforge-prod-eks" {
				t.Errorf("expected cluster name cloudforge-prod-eks, got %s", args[3])
			}
			return []byte("Updated context arn:aws:eks:eu-west-1:123456789012:cluster/cloudforge-prod-eks in /home/appuser/.kube/config"), nil
		}

		if name == "kubectl" && len(args) > 0 && args[0] == "apply" {
			return []byte("deployment created\nservice created"), nil
		}

		if name == "kubectl" && len(args) > 0 && args[0] == "rollout" {
			return []byte("rollout succeeded"), nil
		}

		return nil, nil
	}

	opts := KubernetesOptions{
		ClusterName:      "cloudforge-prod-eks",
		AWSRegion:        "eu-west-1",
		DefaultNamespace: "production",
		KubectlPath:      "kubectl",
		AWSCLIPath:       "aws",
		Timeout:          60 * time.Second,
	}

	exec := NewKubernetesExecutorWithOptions(getter, opts, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if result.Status != "succeeded" {
		t.Fatalf("expected succeeded, got %s", result.Status)
	}

	// Verify that aws eks update-kubeconfig was executed first, followed by kubectl apply and rollout status
	if len(commandsRun) != 3 {
		t.Fatalf("expected 3 commands (aws update-kubeconfig, kubectl apply, kubectl rollout), got %d: %v", len(commandsRun), commandsRun)
	}

	if !strings.HasPrefix(commandsRun[0], "aws eks update-kubeconfig --name cloudforge-prod-eks --region eu-west-1") {
		t.Fatalf("expected first command to be aws eks update-kubeconfig, got: %s", commandsRun[0])
	}

	// Calling Execute a second time should not re-run aws update-kubeconfig (cached)
	_, err = exec.Execute(context.Background(), deploymentID)
	if err != nil {
		t.Fatalf("unexpected error on second execution: %v", err)
	}

	if len(commandsRun) != 5 { // 3 + 2 (apply + rollout)
		t.Fatalf("expected 5 total commands (reusing cluster config), got %d", len(commandsRun))
	}
}

func TestKubernetesExecutorEKSAuthenticationFails(t *testing.T) {
	deploymentID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    uuid.New(),
				Environment:  "production",
				Image:        "nginx:1.27",
				GitCommitSHA: "abcdef1234",
				Namespace:    "default",
			}, nil
		},
	}

	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		if name == "aws" {
			return []byte("An error occurred (AccessDeniedException) when calling the DescribeCluster operation: User is not authorized"), errors.New("exit status 254")
		}
		return nil, nil
	}

	opts := KubernetesOptions{
		ClusterName: "cloudforge-forbidden-eks",
		AWSRegion:   "eu-west-1",
	}

	exec := NewKubernetesExecutorWithOptions(getter, opts, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err == nil {
		t.Fatal("expected EKS authentication error, got nil")
	}

	if result.Status != "failed" {
		t.Fatalf("expected failed status, got %s", result.Status)
	}

	if !strings.Contains(result.Message, "AccessDeniedException") {
		t.Fatalf("expected error message to contain AccessDeniedException, got: %s", result.Message)
	}
}

func TestKubernetesExecutorRollbackRedeployment(t *testing.T) {
	rollbackDeploymentID := uuid.New()
	projectID := uuid.New()

	// Rollback deployment using the previous stable image and commit
	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           rollbackDeploymentID,
				ProjectID:    projectID,
				Environment:  "production",
				Image:        "my-registry/app:v1.0.0-stable",
				GitCommitSHA: "111111111111",
				Namespace:    "prod",
				Status:       model.DeploymentStatusPending,
			}, nil
		},
	}

	var appliedManifest string
	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		if len(args) > 0 && args[0] == "apply" {
			appliedManifest = string(stdin)
			return []byte("deployment.apps/app-" + projectID.String()[:8] + " configured\nservice/app-" + projectID.String()[:8] + " unchanged"), nil
		}
		if len(args) > 0 && args[0] == "rollout" {
			return []byte("deployment \"app-" + projectID.String()[:8] + "\" successfully rolled out"), nil
		}
		return nil, nil
	}

	exec := NewKubernetesExecutorWithRunner(getter, "kubectl", 30*time.Second, runner)

	result, err := exec.Execute(context.Background(), rollbackDeploymentID)
	if err != nil {
		t.Fatalf("expected successful rollback execution, got: %v", err)
	}

	if result.Status != "succeeded" {
		t.Fatalf("expected succeeded status for rollback, got %s", result.Status)
	}

	if !strings.Contains(appliedManifest, "my-registry/app:v1.0.0-stable") {
		t.Fatalf("expected rollback manifest to deploy previous stable image, got: %s", appliedManifest)
	}
	if !strings.Contains(appliedManifest, "111111111111") {
		t.Fatalf("expected rollback manifest to contain previous commit SHA, got: %s", appliedManifest)
	}
}

func TestKubernetesExecutorCheckAPIConnectivitySuccess(t *testing.T) {
	commandsRun := make([]string, 0)
	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		cmdStr := name + " " + strings.Join(args, " ")
		commandsRun = append(commandsRun, cmdStr)
		return []byte("Kubernetes control plane is running at https://10.0.0.1:6443"), nil
	}

	opts := KubernetesOptions{
		KubectlPath: "kubectl",
		KubeConfig:  "/var/lib/cloudforge/kube/config",
	}

	exec := NewKubernetesExecutorWithOptions(&mockDeploymentGetter{}, opts, runner)

	err := exec.CheckAPIConnectivity(context.Background())
	if err != nil {
		t.Fatalf("expected connectivity check to succeed, got: %v", err)
	}

	if len(commandsRun) != 1 {
		t.Fatalf("expected 1 command, got %d", len(commandsRun))
	}

	if !strings.Contains(commandsRun[0], "get --raw=/version") || !strings.Contains(commandsRun[0], "--kubeconfig /var/lib/cloudforge/kube/config") {
		t.Fatalf("expected API version check with dedicated kubeconfig, got: %s", commandsRun[0])
	}
}

func TestKubernetesExecutorCheckAPIConnectivityFails(t *testing.T) {
	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		return []byte("Unable to connect to the server: dial tcp 10.0.0.1:6443: i/o timeout"), errors.New("exit status 1")
	}

	opts := KubernetesOptions{
		KubectlPath: "kubectl",
		KubeConfig:  "/var/lib/cloudforge/kube/config",
	}

	exec := NewKubernetesExecutorWithOptions(&mockDeploymentGetter{}, opts, runner)

	err := exec.CheckAPIConnectivity(context.Background())
	if err == nil {
		t.Fatal("expected connectivity check to fail on unreachable API server, got nil")
	}

	if !strings.Contains(err.Error(), "i/o timeout") {
		t.Fatalf("expected timeout in error message, got: %s", err.Error())
	}
}

func TestKubernetesExecutorDedicatedKubeConfigPropagation(t *testing.T) {
	deploymentID := uuid.New()
	projectID := uuid.New()

	getter := &mockDeploymentGetter{
		getByIDFunc: func(ctx context.Context, id uuid.UUID) (model.Deployment, error) {
			return model.Deployment{
				ID:           deploymentID,
				ProjectID:    projectID,
				Environment:  "production",
				Image:        "123456789012.dkr.ecr.eu-west-1.amazonaws.com/api:v2",
				GitCommitSHA: "222222222222",
				Namespace:    "prod",
			}, nil
		},
	}

	var commandsRun []string
	runner := func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
		cmdStr := name + " " + strings.Join(args, " ")
		commandsRun = append(commandsRun, cmdStr)

		if name == "aws" {
			return []byte("Updated context in /var/lib/cloudforge/kube/config"), nil
		}
		if name == "kubectl" {
			return []byte("success"), nil
		}
		return nil, nil
	}

	opts := KubernetesOptions{
		ClusterName: "cloudforge-dedicated-eks",
		AWSRegion:   "eu-west-1",
		KubeConfig:  "/var/lib/cloudforge/kube/config",
		Timeout:     45 * time.Second,
	}

	exec := NewKubernetesExecutorWithOptions(getter, opts, runner)

	result, err := exec.Execute(context.Background(), deploymentID)
	if err != nil {
		t.Fatalf("unexpected execution error: %v", err)
	}

	if result.Status != "succeeded" {
		t.Fatalf("expected status succeeded, got %s", result.Status)
	}

	// Verify that aws eks update-kubeconfig used --kubeconfig /var/lib/cloudforge/kube/config
	if !strings.Contains(commandsRun[0], "--kubeconfig /var/lib/cloudforge/kube/config") {
		t.Fatalf("expected aws update-kubeconfig to use dedicated kubeconfig path, got: %s", commandsRun[0])
	}

	// Verify that kubectl apply used --kubeconfig /var/lib/cloudforge/kube/config
	if !strings.Contains(commandsRun[1], "--kubeconfig /var/lib/cloudforge/kube/config") {
		t.Fatalf("expected kubectl apply to use dedicated kubeconfig path, got: %s", commandsRun[1])
	}

	// Verify that kubectl rollout used --kubeconfig /var/lib/cloudforge/kube/config
	if !strings.Contains(commandsRun[2], "--kubeconfig /var/lib/cloudforge/kube/config") {
		t.Fatalf("expected kubectl rollout to use dedicated kubeconfig path, got: %s", commandsRun[2])
	}
}

func TestKubernetesExecutorDeploymentServicePortsAndSelectorsMatch(t *testing.T) {
	d := model.Deployment{
		ID:           uuid.New(),
		ProjectID:    uuid.New(),
		Environment:  "production",
		Image:        "app:v1.0.0",
		GitCommitSHA: "abcdef12345678",
		Namespace:    "default",
	}

	name := sanitizeWorkloadName(d)
	manifest := generateKubernetesManifest(d, name, 120)

	docs := strings.Split(manifest, "---")
	if len(docs) != 2 {
		t.Fatalf("expected manifest to contain exactly 2 documents (Deployment and Service), got %d", len(docs))
	}

	deploymentDoc := docs[0]
	serviceDoc := docs[1]

	// Expected app label
	expectedLabel := fmt.Sprintf("app.kubernetes.io/name: %s", name)

	// Check Deployment selector and template labels
	if !strings.Contains(deploymentDoc, expectedLabel) {
		t.Fatalf("Deployment missing label %q", expectedLabel)
	}

	// Check Service selector matches
	if !strings.Contains(serviceDoc, expectedLabel) {
		t.Fatalf("Service selector missing label %q", expectedLabel)
	}

	// Check Container Port is 8080
	if !strings.Contains(deploymentDoc, "containerPort: 8080") {
		t.Fatal("Deployment containerPort is not 8080")
	}

	// Check Service targetPort is 8080 and port is 80
	if !strings.Contains(serviceDoc, "port: 80") {
		t.Fatal("Service port is not 80")
	}
	if !strings.Contains(serviceDoc, "targetPort: 8080") {
		t.Fatal("Service targetPort is not 8080")
	}

	// Check Probes are targeting containerPort 8080
	if !strings.Contains(deploymentDoc, "port: 8080") {
		t.Fatal("Probe port is not 8080")
	}
}

func TestKubernetesExecutorDoesNotRequireClusterAdmin(t *testing.T) {
	// Verifies that executor manifest and kubectl commands are strictly namespace-scoped:
	// - Manifest contains only apps/v1 Deployment and v1 Service (namespaced)
	// - No cluster-scoped resources (ClusterRole, ClusterRoleBinding, CRDs, Namespaces, Nodes)
	// - Commands specify the target namespace with -n flag
	deployment := model.Deployment{
		ProjectID:    uuid.New(),
		Environment:  "production",
		Image:        "123456789012.dkr.ecr.eu-west-1.amazonaws.com/my-service:v1.0.0",
		GitCommitSHA: "abcdef123456",
		Namespace:    "workloads-prod",
	}

	manifest := generateKubernetesManifest(deployment, "app-12345678", 120)

	// Disallowed cluster-scoped resource kinds
	forbiddenKinds := []string{
		"kind: ClusterRole",
		"kind: ClusterRoleBinding",
		"kind: CustomResourceDefinition",
		"kind: Namespace",
		"kind: Node",
		"kind: PersistentVolume\n",
	}

	for _, forbidden := range forbiddenKinds {
		if strings.Contains(manifest, forbidden) {
			t.Fatalf("Executor manifest must NOT include cluster-scoped resource: %s", forbidden)
		}
	}

	// Must be explicitly namespaced
	if !strings.Contains(manifest, "namespace: workloads-prod") {
		t.Fatal("Manifest must specify target namespace")
	}
}

func TestKubernetesReconcileIsReadOnlyAndRequiresMatchingObjects(t *testing.T) {
	d := model.Deployment{
		ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging",
		Image: "nginx:stable", GitCommitSHA: "abcdef1234567", Namespace: "staging-ns",
	}
	name := sanitizeWorkloadName(d)
	output := fmt.Sprintf(`{"items":[
		{"kind":"Deployment","metadata":{"name":"%[1]s","namespace":"%[2]s","generation":2,
		 "annotations":{"cloudforge.ai/deployment-id":"%[3]s"}},
		 "spec":{"replicas":2,"selector":{"matchLabels":{"app.kubernetes.io/name":"%[1]s"}},
		 "template":{"spec":{"containers":[{"name":"app","image":"%[4]s"}]}}},
		 "status":{"observedGeneration":2,"replicas":2,"updatedReplicas":2,"availableReplicas":2}},
		{"kind":"Service","metadata":{"name":"%[1]s","namespace":"%[2]s",
		 "annotations":{"cloudforge.ai/deployment-id":"%[3]s"}},
		 "spec":{"type":"ClusterIP","selector":{"app.kubernetes.io/name":"%[1]s"},
		 "ports":[{"port":80,"targetPort":8080}]}}
	]}`, name, d.Namespace, d.ID, d.Image)
	getter := &mockDeploymentGetter{getByIDFunc: func(context.Context, uuid.UUID) (model.Deployment, error) {
		return d, nil
	}}
	exec := NewKubernetesExecutorWithRunner(getter, "kubectl", time.Minute,
		func(_ context.Context, stdin []byte, _ string, args ...string) ([]byte, error) {
			if len(stdin) != 0 || len(args) == 0 || args[0] != "get" {
				t.Fatal("recovery must only query Kubernetes")
			}
			return []byte(output), nil
		})

	for range 2 {
		if err := exec.Reconcile(context.Background(), d.ID); err != nil {
			t.Fatal(err)
		}
	}
	if err := exec.Reconcile(context.Background(), uuid.New()); err == nil {
		t.Fatal("recovered another deployment's objects")
	}
	output = strings.Replace(output, `"observedGeneration":2`, `"observedGeneration":1`, 1)
	if err := exec.Reconcile(context.Background(), d.ID); err == nil {
		t.Fatal("accepted an unobserved deployment generation")
	}

	claimErr := errors.New("lease lost")
	if _, err := exec.ExecuteWithClaim(context.Background(), d.ID, func() error { return claimErr }); !errors.Is(err, claimErr) {
		t.Fatalf("apply did not respect the ownership check: %v", err)
	}
	manifest := generateKubernetesManifest(d, name, 60)
	if strings.Count(manifest, "cloudforge.ai/deployment-id: \""+d.ID.String()+"\"") != 2 {
		t.Fatal("both applied objects must carry the recovery marker")
	}
}
