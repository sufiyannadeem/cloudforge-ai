package executor

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

var (
	dns1123LabelRegex = regexp.MustCompile(`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`)
	awsRegionRegex    = regexp.MustCompile(`^[a-z]{2}-[a-z]+-\d+$`)
	dockerImageRegex  = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_.-]*(/[a-zA-Z0-9_.-]+)*(:[a-zA-Z0-9_.-]+)?(@sha256:[a-fA-F0-9]{64})?$`)
	commitSHARegex    = regexp.MustCompile(`^[a-fA-F0-9]{7,64}$`)
)

// DeploymentGetter provides access to deployment records for execution.
type DeploymentGetter interface {
	GetByID(ctx context.Context, id uuid.UUID) (model.Deployment, error)
}

// CommandRunner executes a command with stdin input and returns combined output.
type CommandRunner func(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error)

func defaultCommandRunner(ctx context.Context, stdin []byte, name string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.WaitDelay = 2 * time.Second
	if len(stdin) > 0 {
		cmd.Stdin = bytes.NewReader(stdin)
	}

	var output limitedCommandBuffer
	cmd.Stdout, cmd.Stderr = &output, &output
	if err := cmd.Run(); err != nil {
		return output.Bytes(), err
	}
	if output.overflow {
		return nil, errors.New("command output exceeded the limit")
	}
	return output.Bytes(), nil
}

type limitedCommandBuffer struct {
	bytes.Buffer
	overflow bool
}

func (b *limitedCommandBuffer) Write(data []byte) (int, error) {
	size := len(data)
	if remaining := (1 << 20) - b.Len(); size > remaining {
		b.overflow = true
		data = data[:remaining]
	}
	_, _ = b.Buffer.Write(data)
	return size, nil
}

// KubernetesOptions provides configuration for Kubernetes / EKS workload deployment.
type KubernetesOptions struct {
	ArgoEnabled      bool
	AnalysisTemplate string
	ClusterName      string
	AWSRegion        string
	DefaultNamespace string
	KubectlPath      string
	AWSCLIPath       string
	KubeConfig       string
	Timeout          time.Duration
}

// KubernetesExecutor performs real workload delivery to Kubernetes / EKS clusters.
type KubernetesExecutor struct {
	argoEnabled      bool
	analysisTemplate string
	deploymentGetter DeploymentGetter
	kubectlPath      string
	awsCLIPath       string
	kubeconfigPath   string
	clusterName      string
	awsRegion        string
	defaultNamespace string
	timeout          time.Duration
	runner           CommandRunner
	configured       bool
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
	return NewKubernetesExecutorWithOptions(getter, KubernetesOptions{
		KubectlPath: kubectlPath,
		Timeout:     timeout,
	}, runner)
}

// NewProductionKubernetesExecutor creates an executor configured for production EKS deployment.
func NewProductionKubernetesExecutor(
	getter DeploymentGetter,
	opts KubernetesOptions,
) (*KubernetesExecutor, error) {
	if getter == nil {
		return nil, errors.New("deployment getter is required")
	}

	return NewKubernetesExecutorWithOptions(getter, opts, defaultCommandRunner), nil
}

// NewKubernetesExecutorWithOptions creates an executor with full option customization and runner injection.
func NewKubernetesExecutorWithOptions(
	getter DeploymentGetter,
	opts KubernetesOptions,
	runner CommandRunner,
) *KubernetesExecutor {
	kubectlPath := strings.TrimSpace(opts.KubectlPath)
	if kubectlPath == "" {
		kubectlPath = "kubectl"
	}

	awsCLIPath := strings.TrimSpace(opts.AWSCLIPath)
	if awsCLIPath == "" {
		awsCLIPath = "aws"
	}

	timeout := opts.Timeout
	if timeout <= 0 {
		timeout = 120 * time.Second
	}

	defaultNamespace := strings.TrimSpace(opts.DefaultNamespace)
	if defaultNamespace == "" {
		defaultNamespace = "default"
	}

	region := strings.TrimSpace(opts.AWSRegion)
	if region == "" {
		region = "eu-west-1"
	}

	if runner == nil {
		runner = defaultCommandRunner
	}

	return &KubernetesExecutor{
		deploymentGetter: getter,
		argoEnabled:      opts.ArgoEnabled, analysisTemplate: opts.AnalysisTemplate,
		kubectlPath:      kubectlPath,
		awsCLIPath:       awsCLIPath,
		kubeconfigPath:   strings.TrimSpace(opts.KubeConfig),
		clusterName:      strings.TrimSpace(opts.ClusterName),
		awsRegion:        region,
		defaultNamespace: defaultNamespace,
		timeout:          timeout,
		runner:           runner,
	}
}

// EnsureClusterConfig verifies or updates kubeconfig for the target EKS cluster using AWS IAM workload credentials.
func (k *KubernetesExecutor) EnsureClusterConfig(ctx context.Context) error {
	if k.configured {
		return nil
	}

	// If no EKS cluster name is configured, assume pre-configured KUBECONFIG or in-cluster credentials
	if k.clusterName == "" {
		k.configured = true
		return nil
	}

	// Validate cluster name and AWS region to prevent shell or argument injection
	if err := validateClusterName(k.clusterName); err != nil {
		return fmt.Errorf("invalid cluster name %q: %w", k.clusterName, err)
	}

	if err := validateAWSRegion(k.awsRegion); err != nil {
		return fmt.Errorf("invalid AWS region %q: %w", k.awsRegion, err)
	}

	args := []string{
		"eks",
		"update-kubeconfig",
		"--name",
		k.clusterName,
		"--region",
		k.awsRegion,
	}

	if k.kubeconfigPath != "" {
		args = append(args, "--kubeconfig", k.kubeconfigPath)
	}

	output, err := k.runner(
		ctx,
		nil,
		k.awsCLIPath,
		args...,
	)
	if err != nil {
		errMsg := strings.TrimSpace(string(output))
		if errMsg == "" {
			errMsg = err.Error()
		}
		return fmt.Errorf("EKS authentication failed for cluster %q in region %q: %s", k.clusterName, k.awsRegion, errMsg)
	}

	k.configured = true
	return nil
}

// CheckAPIConnectivity verifies actual live connectivity to the Kubernetes API server.
func (k *KubernetesExecutor) CheckAPIConnectivity(ctx context.Context) error {
	// Check the API server without listing services in kube-system.
	args := []string{"get", "--raw=/version", "--request-timeout=10s"}
	if k.kubeconfigPath != "" {
		args = append(args, "--kubeconfig", k.kubeconfigPath)
	}

	output, err := k.runner(ctx, nil, k.kubectlPath, args...)
	if err != nil {
		errMsg := strings.TrimSpace(string(output))
		if errMsg == "" {
			errMsg = err.Error()
		}
		return fmt.Errorf("Kubernetes API connectivity check failed: %s", errMsg)
	}

	return nil
}

// Execute deploys the container workload to Kubernetes and waits for rollout health.
func (k *KubernetesExecutor) Execute(
	ctx context.Context,
	deploymentID uuid.UUID,
) (Result, error) {
	return k.ExecuteWithClaim(ctx, deploymentID, nil)
}

// ExecuteWithClaim checks ownership immediately before the first cluster mutation.
func (k *KubernetesExecutor) ExecuteWithClaim(
	ctx context.Context,
	deploymentID uuid.UUID,
	claim func() error,
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

	// Apply default namespace if missing
	if strings.TrimSpace(deployment.Namespace) == "" {
		deployment.Namespace = k.defaultNamespace
	}

	// Validate user-controlled and deployment values
	if err := validateDeploymentForExecution(deployment); err != nil {
		return Result{
			DeploymentID: deploymentID,
			Status:       "failed",
			Message:      fmt.Sprintf("validation failed: %v", err),
			Duration:     time.Since(start),
		}, fmt.Errorf("validate deployment: %w", err)
	}

	// Ensure EKS cluster connection is configured
	if err := k.EnsureClusterConfig(ctx); err != nil {
		return Result{
			DeploymentID: deploymentID,
			Status:       "failed",
			Message:      fmt.Sprintf("cluster authentication failed: %v", err),
			Duration:     time.Since(start),
		}, fmt.Errorf("cluster authentication: %w", err)
	}

	progressiveHistory := false
	if !deployment.Strategy.Progressive() {
		if history, ok := k.deploymentGetter.(interface {
			HasProgressiveHistory(context.Context, uuid.UUID) (bool, error)
		}); ok {
			progressiveHistory, err = history.HasProgressiveHistory(ctx, deploymentID)
			if err != nil {
				return Result{}, errors.New("deployment strategy history could not be verified")
			}
		}
	}
	if !deployment.Strategy.Progressive() && (k.argoEnabled || progressiveHistory) {
		data, err := k.readScoped(ctx, deployment.Namespace, "api-resources", "--api-group=argoproj.io", "-o", "name")
		if err != nil {
			return Result{}, ErrRolloutUnavailable
		}
		if progressiveHistory && !strings.Contains(string(data), "rollouts.argoproj.io") {
			return Result{}, errors.New("progressive history exists but Argo resources cannot be checked; reconcile before native execution")
		}
		if strings.Contains(string(data), "rollouts.argoproj.io") {
			existing, err := k.readScoped(ctx, deployment.Namespace, "get", "rollouts.argoproj.io", sanitizeWorkloadName(deployment), "--ignore-not-found", "-o", "json")
			if err != nil || len(strings.TrimSpace(string(existing))) > 0 {
				return Result{}, errors.New("Argo Rollout exists for this workload; independent migration required before native rolling")
			}
		}
	}
	var prepared argoObject
	if deployment.Strategy.Progressive() {
		prepared, err = k.prepareArgo(ctx, deployment)
		if err != nil {
			return Result{}, err
		}
	}
	workloadName := sanitizeWorkloadName(deployment)
	manifest := generateKubernetesManifest(deployment, workloadName, int(k.timeout.Seconds()))
	if deployment.Strategy.Progressive() {
		manifest = k.argoManifest(deployment)
		manifest = strings.Replace(manifest, "metadata:\n", fmt.Sprintf("metadata:\n  resourceVersion: %q\n  uid: %q\n", prepared.Metadata.ResourceVersion, prepared.Metadata.UID), 1)
	}

	// Step 1: Apply workload manifest (Deployment and corresponding Service) to cluster
	applyArgs := []string{"apply", "-f", "-", "-n", deployment.Namespace}
	if deployment.Strategy.Progressive() {
		applyArgs = append(applyArgs, "--server-side", "--field-manager=cloudforge-rollouts")
	}
	if k.kubeconfigPath != "" {
		applyArgs = append(applyArgs, "--kubeconfig", k.kubeconfigPath)
	}

	if claim != nil {
		if err := claim(); err != nil {
			return Result{}, err
		}
	}
	if err := ctx.Err(); err != nil {
		return Result{}, err
	}
	applyCtx, cancelApply := context.WithTimeout(ctx, k.timeout)
	applyOutput, err := k.runner(
		applyCtx,
		[]byte(manifest),
		k.kubectlPath,
		applyArgs...,
	)
	cancelApply()
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

	if deployment.Strategy.Progressive() {
		err := k.waitArgo(ctx, deploymentID)
		if err != nil {
			return Result{}, err
		}
		return Result{DeploymentID: deploymentID, Status: "succeeded", Message: "Argo confirmed healthy revision", Duration: time.Since(start)}, nil
	}
	// Step 2: Track rollout status until ready or deadline exceeded
	timeoutStr := fmt.Sprintf("%ds", int(k.timeout.Seconds()))
	rolloutArgs := []string{
		"rollout",
		"status",
		fmt.Sprintf("deployment/%s", workloadName),
		"-n",
		deployment.Namespace,
		fmt.Sprintf("--timeout=%s", timeoutStr),
	}
	if k.kubeconfigPath != "" {
		rolloutArgs = append(rolloutArgs, "--kubeconfig", k.kubeconfigPath)
	}

	rolloutOutput, err := k.runner(
		ctx,
		nil,
		k.kubectlPath,
		rolloutArgs...,
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
		Message:      fmt.Sprintf("Rollout succeeded for %s: pods and service ready", deployment.Image),
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

func generateKubernetesManifest(d model.Deployment, name string, deadlineSeconds int) string {
	if deadlineSeconds <= 0 {
		deadlineSeconds = 120
	}
	// Kubernetes requires progressDeadlineSeconds > minReadySeconds.
	if deadlineSeconds <= 10 {
		deadlineSeconds = 11
	}
	podSecurity := ""
	if d.Namespace == "cf-"+d.ProjectID.String() {
		podSecurity = "      automountServiceAccountToken: false\n"
	}

	if len(d.Strategy.ReadinessGates) > 0 {
		podSecurity += "      readinessGates:\n"
		for _, gate := range d.Strategy.ReadinessGates {
			podSecurity += "      - conditionType: " + gate + "\n"
		}
	}
	manifest := fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: %s
  namespace: %s
  annotations:
    cloudforge.ai/deployment-id: "%s"
  labels:
    app.kubernetes.io/name: %s
    app.kubernetes.io/instance: %s
    app.kubernetes.io/version: %s
    app.kubernetes.io/managed-by: cloudforge-ai
    cloudforge.ai/environment: %s
    cloudforge.ai/project-id: %s
spec:
  replicas: 2
  minReadySeconds: 10
  progressDeadlineSeconds: %d
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: %d
      maxUnavailable: %d
  selector:
    matchLabels:
      app.kubernetes.io/name: %s
  template:
    metadata:
      annotations:
        cloudforge.ai/revision-id: "%s"
      labels:
        app.kubernetes.io/name: %s
        app.kubernetes.io/instance: %s
        app.kubernetes.io/version: %s
        cloudforge.ai/environment: %s
        cloudforge.ai/project-id: %s
    spec:
%s      containers:
      - name: app
        image: %s
        imagePullPolicy: IfNotPresent
        ports:
        - name: http
          containerPort: 8080
          protocol: TCP
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
        startupProbe:
          httpGet:
            path: /health
            port: 8080
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 12
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 20
          timeoutSeconds: 3
          failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: %s
  namespace: %s
  annotations:
    cloudforge.ai/deployment-id: "%s"
  labels:
    app.kubernetes.io/name: %s
    app.kubernetes.io/instance: %s
    app.kubernetes.io/managed-by: cloudforge-ai
    cloudforge.ai/environment: %s
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: %s
  ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
`,
		// Deployment metadata
		name, d.Namespace, d.ID, name, name, d.GitCommitSHA, d.Environment, d.ProjectID,
		// spec
		deadlineSeconds, d.Strategy.Normalized().MaxSurge, d.Strategy.Normalized().MaxUnavailable, name,
		// template metadata
		d.ID, name, name, d.GitCommitSHA, d.Environment, d.ProjectID,
		// container
		podSecurity, d.Image,
		// Service metadata
		name, d.Namespace, d.ID, name, name, d.Environment,
		// Service spec selector
		name,
	)
	// Soft spreading preserves single-node development and existing application
	// scheduling while preferring separate hosts/zones in capable clusters.
	reliability := fmt.Sprintf(`    spec:
      terminationGracePeriodSeconds: 60
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app.kubernetes.io/name: %s
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app.kubernetes.io/name: %s
`, name, name)
	return strings.Replace(manifest, "    spec:\n", reliability, 1)

}

func validateClusterName(name string) error {
	name = strings.TrimSpace(name)
	if name == "" {
		return errors.New("cluster name cannot be empty")
	}
	if len(name) > 100 {
		return errors.New("cluster name exceeds maximum 100 characters")
	}
	if !dns1123LabelRegex.MatchString(name) {
		return errors.New("cluster name must be a valid DNS-1123 subdomain label (lowercase alphanumeric and hyphens)")
	}
	return nil
}

func validateAWSRegion(region string) error {
	region = strings.TrimSpace(region)
	if region == "" {
		return errors.New("AWS region cannot be empty")
	}
	if !awsRegionRegex.MatchString(region) {
		return errors.New("AWS region format is invalid (e.g. eu-west-1, us-east-1)")
	}
	return nil
}

func validateDeploymentForExecution(d model.Deployment) error {
	if d.Strategy.Progressive() && !regexp.MustCompile(`@sha256:[a-f0-9]{64}$`).MatchString(d.Image) {
		return errors.New("progressive delivery requires an immutable sha256 image")
	}
	if d.Strategy.Progressive() && d.Namespace != "cf-"+d.ProjectID.String() {
		return errors.New("progressive delivery requires the verified project namespace")
	}
	if err := d.Strategy.Validate(); err != nil {
		return err
	}
	if d.ProjectID == uuid.Nil {
		return errors.New("project ID cannot be nil")
	}

	ns := strings.TrimSpace(d.Namespace)
	if ns == "" {
		return errors.New("namespace cannot be empty")
	}
	if len(ns) > 63 || !dns1123LabelRegex.MatchString(ns) {
		return fmt.Errorf("invalid namespace %q: must be a valid RFC 1123 DNS label (<= 63 lowercase alphanumeric characters or hyphens)", d.Namespace)
	}

	img := strings.TrimSpace(d.Image)
	if img == "" {
		return errors.New("container image cannot be empty")
	}
	if strings.ContainsAny(img, " \t\r\n'\"`$<>;|&") || !dockerImageRegex.MatchString(img) {
		return fmt.Errorf("invalid container image %q", d.Image)
	}

	commit := strings.TrimSpace(d.GitCommitSHA)
	if commit == "" {
		return errors.New("git commit SHA cannot be empty")
	}
	if !commitSHARegex.MatchString(commit) {
		return fmt.Errorf("invalid git commit SHA %q: must be 7-64 hex characters", d.GitCommitSHA)
	}

	env := strings.TrimSpace(d.Environment)
	if env != "development" && env != "staging" && env != "production" {
		if !dns1123LabelRegex.MatchString(env) {
			return fmt.Errorf("invalid environment name %q", d.Environment)
		}
	}

	return nil
}
