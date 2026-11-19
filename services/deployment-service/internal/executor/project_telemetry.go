package executor

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

var ErrTelemetryUnavailable = errors.New("verified deployment telemetry unavailable")

type ProjectLogs struct {
	Lines    []string `json:"lines"`
	Page     int      `json:"page"`
	NextPage *int     `json:"next_page"`
}

type ProjectHealth struct {
	Desired            *int   `json:"desired_replicas"`
	Available          *int   `json:"available_replicas"`
	SampledPodRestarts *int64 `json:"sampled_pod_restarts"`
}

type kubeOwner struct {
	Kind, Name, UID string
	Controller      bool
}

type kubeObject struct {
	Kind     string
	Metadata struct {
		Name, Namespace, UID string
		Labels, Annotations  map[string]string
		OwnerReferences      []kubeOwner
		Generation           int64
		DeletionTimestamp    *string
		CreationTimestamp    time.Time
	}
	Spec struct {
		Replicas   *int
		Containers []struct{ Name, Image string }
	}
	Status struct {
		ObservedGeneration observedGeneration
		AvailableReplicas  int
		Phase              string
		Conditions         []struct{ Type, Status, Reason string }
		ContainerStatuses  []struct {
			Name         string
			Ready        *bool
			RestartCount *int
			State        struct {
				Waiting, Terminated *struct{ Reason string }
			}
			LastState struct {
				Terminated *struct{ Reason string }
			}
		}
	}
}

type observedGeneration int64

func (g *observedGeneration) UnmarshalJSON(data []byte) error {
	value, err := strconv.ParseInt(strings.Trim(string(data), "\""), 10, 64)
	*g = observedGeneration(value)
	return err
}

func owns(object kubeObject, kind, name, id string) bool {
	for _, owner := range object.Metadata.OwnerReferences {
		if owner.Controller && owner.Kind == kind && owner.Name == name && owner.UID == id {
			return true
		}
	}
	return false
}

func (k *KubernetesExecutor) readScoped(ctx context.Context, namespace string, args ...string) ([]byte, error) {
	args = append(args, "-n", namespace, "--request-timeout=5s")
	if k.kubeconfigPath != "" {
		args = append(args, "--kubeconfig", k.kubeconfigPath)
	}
	data, err := k.runner(ctx, nil, k.kubectlPath, args...)
	if err != nil || len(data) > 1<<20 {
		return nil, ErrTelemetryUnavailable
	}
	return data, nil
}

func matchesScopedObject(object kubeObject, deployment model.Deployment) bool {
	_, uidErr := uuid.Parse(object.Metadata.UID)
	return uidErr == nil && object.Metadata.Namespace == deployment.Namespace &&
		dns1123LabelRegex.MatchString(object.Metadata.Name) && len(object.Metadata.Name) <= 253 &&
		object.Metadata.DeletionTimestamp == nil &&
		object.Metadata.Labels["cloudforge.ai/project-id"] == deployment.ProjectID.String() &&
		object.Metadata.Labels["cloudforge.ai/environment"] == deployment.Environment
}

func matchesPod(item kubeObject, deployment model.Deployment) bool {
	if item.Kind != "Pod" || !matchesScopedObject(item, deployment) ||
		item.Metadata.Annotations["cloudforge.ai/revision-id"] != deployment.ID.String() {
		return false
	}
	for _, container := range item.Spec.Containers {
		if container.Name == "app" && container.Image == deployment.Image {
			return true
		}
	}
	return false
}

func (k *KubernetesExecutor) scopedPods(ctx context.Context, id uuid.UUID) (model.Deployment, kubeObject, []kubeObject, error) {
	var workload kubeObject
	deployment, err := k.deploymentGetter.GetByID(ctx, id)
	if err != nil || deployment.Namespace != "cf-"+deployment.ProjectID.String() ||
		validateDeploymentForExecution(deployment) != nil || (k.clusterName != "" && !k.configured) {
		return deployment, workload, nil, ErrTelemetryUnavailable
	}
	name := sanitizeWorkloadName(deployment)
	kind, resource := "Deployment", "deployment"
	if deployment.Strategy.Progressive() {
		kind, resource = "Rollout", "rollouts.argoproj.io"
	}
	data, err := k.readScoped(ctx, deployment.Namespace, "get", resource, name, "-o", "json")
	if err != nil || json.Unmarshal(data, &workload) != nil || workload.Kind != kind ||
		workload.Metadata.Name != name || !matchesScopedObject(workload, deployment) ||
		workload.Metadata.Annotations["cloudforge.ai/deployment-id"] != id.String() {
		return deployment, workload, nil, ErrTelemetryUnavailable
	}

	selector := "app.kubernetes.io/name=" + name + ",cloudforge.ai/project-id=" + deployment.ProjectID.String()
	data, err = k.readScoped(ctx, deployment.Namespace, "get", "replicasets,pods", "-l", selector, "-o", "json")
	var objects struct{ Items []kubeObject }
	if err != nil || json.Unmarshal(data, &objects) != nil || len(objects.Items) > 150 {
		return deployment, workload, nil, ErrTelemetryUnavailable
	}
	sets := make(map[string]string)
	for _, item := range objects.Items {
		if item.Kind == "ReplicaSet" && matchesScopedObject(item, deployment) &&
			owns(item, kind, name, workload.Metadata.UID) {
			sets[item.Metadata.UID] = item.Metadata.Name
		}
	}
	pods := make([]kubeObject, 0)
	for _, item := range objects.Items {
		if matchesPod(item, deployment) {
			for uid, name := range sets {
				if owns(item, "ReplicaSet", name, uid) {
					pods = append(pods, item)
					break
				}
			}
		}
	}
	sort.Slice(pods, func(i, j int) bool { return pods[i].Metadata.Name < pods[j].Metadata.Name })
	return deployment, workload, pods, nil
}

func (k *KubernetesExecutor) ProjectLogs(ctx context.Context, id uuid.UUID, page, lines int) (ProjectLogs, error) {
	if page < 0 || page >= 24 || lines < 1 || lines > 200 {
		return ProjectLogs{}, ErrTelemetryUnavailable
	}
	ctx, cancel := context.WithTimeout(ctx, 12*time.Second)
	defer cancel()
	d, _, pods, err := k.scopedPods(ctx, id)
	if err != nil {
		return ProjectLogs{}, err
	}
	result := ProjectLogs{Lines: []string{}, Page: page}
	if page >= len(pods) {
		return result, nil
	}
	result.Lines, err = k.recentPodLogs(ctx, d, pods[page], lines)
	if err != nil {
		return ProjectLogs{}, err
	}
	if page+1 < len(pods) && page+1 < 24 {
		next := page + 1
		result.NextPage = &next
	}
	return result, nil
}

func (k *KubernetesExecutor) recentPodLogs(ctx context.Context, d model.Deployment, pod kubeObject, lines int) ([]string, error) {
	raw, err := k.readScoped(ctx, d.Namespace, "logs", pod.Metadata.Name, "-c", "app",
		"--tail="+strconv.Itoa(lines), "--since=15m", "--limit-bytes=16384")
	if err != nil || len(raw) > 16384 || !k.podStillOwned(ctx, d, pod) {
		return nil, ErrTelemetryUnavailable
	}
	return redactProjectLogs(raw, lines), nil
}

// Pod names can be reused. Recheck UID and owner after sampling name-addressed data.
func (k *KubernetesExecutor) podStillOwned(ctx context.Context, d model.Deployment, pod kubeObject) bool {
	data, err := k.readScoped(ctx, d.Namespace, "get", "pod", pod.Metadata.Name, "-o", "json")
	var refreshed kubeObject
	if err != nil || json.Unmarshal(data, &refreshed) != nil || !matchesPod(refreshed, d) ||
		refreshed.Metadata.UID != pod.Metadata.UID || refreshed.Metadata.Name != pod.Metadata.Name {
		return false
	}
	for _, owner := range pod.Metadata.OwnerReferences {
		if owner.Controller && owner.Kind == "ReplicaSet" {
			return owns(refreshed, owner.Kind, owner.Name, owner.UID)
		}
	}
	return false
}

var sensitiveLog = regexp.MustCompile(`(?i)(password|passwd|secret|credential|authorization|bearer|api[_-]?key|token|cookie|private.?key|session[_-]?id|access[_-]?key|signature|dsn)`)
var credentialToken = regexp.MustCompile(`(?i)(AKIA|ASIA)[A-Z0-9]{16}|[[:alnum:]_-]{45,}|[[:alnum:]_+=/]{40,}|eyJ[[:alnum:]_-]+\.[[:alnum:]_-]+\.[[:alnum:]_-]+|[a-z]+://[^/[:space:]]+@|-----BEGIN|-----END`)

func redactProjectLogs(data []byte, limit int) []string {
	lines := strings.Split(strings.ToValidUTF8(string(data), "\uFFFD"), "\n")
	// Kubernetes may start a byte-limited response in the middle of a credential.
	if len(data) >= 16384 && len(lines) > 0 {
		lines = lines[1:]
	}
	result := make([]string, 0, min(limit, len(lines)))
	inKey := false
	for _, line := range lines {
		if len(result) >= limit {
			break
		}
		if strings.Contains(line, "-----BEGIN") {
			inKey = true
		}
		if inKey || len(line) > 1024 || sensitiveLog.MatchString(line) || credentialToken.MatchString(line) {
			result = append(result, "[redacted]")
		} else if strings.TrimSpace(line) != "" {
			result = append(result, line)
		}
		if strings.Contains(line, "-----END") {
			inKey = false
		}
	}
	return result
}

func (k *KubernetesExecutor) ProjectHealth(ctx context.Context, id uuid.UUID, prometheusURL string) (ProjectHealth, error) {
	ctx, cancel := context.WithTimeout(ctx, 12*time.Second)
	defer cancel()
	d, workload, pods, err := k.scopedPods(ctx, id)
	if err != nil {
		return ProjectHealth{}, err
	}
	health := ProjectHealth{Desired: workload.Spec.Replicas}
	if workload.Metadata.Generation > 0 && int64(workload.Status.ObservedGeneration) == workload.Metadata.Generation {
		health.Available = &workload.Status.AvailableReplicas
	}
	if len(pods) > 0 {
		health.SampledPodRestarts = podRestarts(ctx, prometheusURL, d.Namespace, pods[0])
	}
	return health, nil
}

func podRestarts(ctx context.Context, baseURL, namespace string, pod kubeObject) *int64 {
	u, err := url.Parse(baseURL)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") {
		return nil
	}
	u.Path = "/api/v1/query"
	selector := fmt.Sprintf(`kube_pod_container_status_restarts_total{namespace=%q,pod=%q,uid=%q,container="app"}`, namespace, pod.Metadata.Name, pod.Metadata.UID)
	q := url.Values{"query": {selector + " and (time() - timestamp(" + selector + ") <= 120)"}}
	u.RawQuery = q.Encode()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil
	}
	client := http.Client{Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(request)
	if err != nil {
		return nil
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil
	}
	return parsePodRestarts(response.Body, namespace, pod, time.Now())
}

func parsePodRestarts(body io.Reader, namespace string, pod kubeObject, now time.Time) *int64 {
	var data struct {
		Status string
		Data   struct {
			ResultType string
			Result     []struct {
				Metric map[string]string
				Value  []json.RawMessage
			}
		}
	}
	if json.NewDecoder(io.LimitReader(body, 16<<10)).Decode(&data) != nil ||
		data.Status != "success" || data.Data.ResultType != "vector" || len(data.Data.Result) != 1 {
		return nil
	}
	sample := data.Data.Result[0]
	if sample.Metric["__name__"] != "kube_pod_container_status_restarts_total" || sample.Metric["uid"] != pod.Metadata.UID || sample.Metric["namespace"] != namespace ||
		sample.Metric["pod"] != pod.Metadata.Name || sample.Metric["container"] != "app" || len(sample.Value) != 2 {
		return nil
	}
	var timestamp float64
	var raw string
	if json.Unmarshal(sample.Value[0], &timestamp) != nil || json.Unmarshal(sample.Value[1], &raw) != nil ||
		math.Abs(float64(now.Unix())-timestamp) > 120 {
		return nil
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || value < 0 {
		return nil
	}
	return &value
}
