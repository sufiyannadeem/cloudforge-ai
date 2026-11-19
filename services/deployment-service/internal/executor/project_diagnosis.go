package executor

import (
	"context"
	"encoding/json"
	"regexp"
	"slices"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type ProjectDiagnosis struct {
	Source         string     `json:"source"`
	ObservedAt     time.Time  `json:"observed_at"`
	Desired        *int       `json:"desired_replicas"`
	Available      *int       `json:"available_replicas"`
	Sample         *PodSample `json:"sample"`
	Severity       string     `json:"severity"`
	LikelyCause    string     `json:"likely_cause"`
	Recommendation string     `json:"recommendation"`
}

type PodSample struct {
	Name           string    `json:"name"`
	Phase          string    `json:"phase"`
	Ready          *bool     `json:"ready"`
	Restarts       *int      `json:"restarts"`
	Reasons        []string  `json:"reasons"`
	EventsChecked  bool      `json:"events_checked"`
	LogsChecked    bool      `json:"logs_checked"`
	LogErrorSignal bool      `json:"log_error_signal"`
	Usage          *PodUsage `json:"usage"`
}

type PodUsage struct {
	CPU       string    `json:"cpu"`
	Memory    string    `json:"memory"`
	Timestamp time.Time `json:"timestamp"`
}

func (k *KubernetesExecutor) DiagnoseProject(ctx context.Context, id uuid.UUID) (ProjectDiagnosis, error) {
	ctx, cancel := context.WithTimeout(ctx, 18*time.Second)
	defer cancel()
	d, workload, pods, err := k.scopedPods(ctx, id)
	if err != nil || d.ExecutionMode == "simulated" {
		return ProjectDiagnosis{}, ErrTelemetryUnavailable
	}
	result := ProjectDiagnosis{Source: "live_kubernetes", ObservedAt: time.Now().UTC(), Desired: workload.Spec.Replicas}
	observed := workload.Metadata.Generation > 0 && workload.Status.ObservedGeneration == workload.Metadata.Generation
	deadline := false
	if observed {
		result.Available = &workload.Status.AvailableReplicas
		for _, c := range workload.Status.Conditions {
			deadline = deadline || c.Type == "Progressing" && c.Status == "False" && c.Reason == "ProgressDeadlineExceeded"
		}
	}
	if len(pods) > 0 {
		// Prefer an unready pod. Bound event, log and usage reads to one pod.
		pod := pods[0]
		for _, candidate := range pods {
			ready, _, _ := appStatus(candidate)
			if ready != nil && !*ready {
				pod = candidate
				break
			}
		}
		result.Sample = k.samplePod(ctx, d, pod)
	}
	describeDiagnosis(&result, deadline)
	return result, nil
}

func appStatus(pod kubeObject) (*bool, *int, []string) {
	reasons := []string{}
	for _, container := range pod.Status.ContainerStatuses {
		if container.Name != "app" {
			continue
		}
		for _, state := range []*struct{ Reason string }{container.State.Waiting, container.State.Terminated, container.LastState.Terminated} {
			if state != nil {
				reasons = appendReason(reasons, state.Reason)
			}
		}
		return container.Ready, container.RestartCount, reasons
	}
	return nil, nil, reasons
}

func appendReason(reasons []string, reason string) []string {
	switch reason {
	case "OOMKilled", "CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "FailedScheduling", "FailedMount", "Unhealthy", "BackOff", "CreateContainerConfigError":
		if !slices.Contains(reasons, reason) {
			return append(reasons, reason)
		}
	}
	return reasons
}

func (k *KubernetesExecutor) samplePod(ctx context.Context, d model.Deployment, pod kubeObject) *PodSample {
	ready, restarts, reasons := appStatus(pod)
	sample := &PodSample{Name: pod.Metadata.Name, Ready: ready, Restarts: restarts, Reasons: reasons}
	if slices.Contains([]string{"Pending", "Running", "Succeeded", "Failed", "Unknown"}, pod.Status.Phase) {
		sample.Phase = pod.Status.Phase
	}
	raw, err := k.readScoped(ctx, d.Namespace, "get", "events", "--field-selector", "involvedObject.uid="+pod.Metadata.UID+",type=Warning", "-o", "json")
	var events struct {
		Items []struct {
			Reason         string
			Type           string
			InvolvedObject struct{ Name, Namespace, UID, Kind string }
		}
	}
	if err == nil && json.Unmarshal(raw, &events) == nil && events.Items != nil {
		sample.EventsChecked = true
		for _, event := range events.Items {
			ref := event.InvolvedObject
			if event.Type == "Warning" && ref.Kind == "Pod" && ref.UID == pod.Metadata.UID && ref.Namespace == d.Namespace && ref.Name == pod.Metadata.Name {
				sample.Reasons = appendReason(sample.Reasons, event.Reason)
			}
		}
	}
	sample.Usage = k.podUsage(ctx, d.Namespace, pod)
	if lines, err := k.recentPodLogs(ctx, d, pod, 30); err == nil {
		sample.LogsChecked = true
		for _, line := range lines {
			text := strings.ToLower(line)
			if strings.Contains(text, "panic:") || strings.Contains(text, "fatal:") {
				sample.LogErrorSignal = true
			}
		}
	} else if !k.podStillOwned(ctx, d, pod) {
		return nil
	}
	return sample
}

var usageQuantity = regexp.MustCompile(`^[0-9]{1,14}(\.[0-9]{1,8})?(n|u|m|Ki|Mi|Gi|Ti)?$`)

func (k *KubernetesExecutor) podUsage(ctx context.Context, namespace string, pod kubeObject) *PodUsage {
	path := "/namespaces/" + namespace + "/pods/" + pod.Metadata.Name
	raw, err := k.readScoped(ctx, namespace, "get", "--raw", "/apis/metrics.k8s.io/v1beta1"+path)
	if err != nil {
		raw, err = k.readScoped(ctx, namespace, "get", "--raw", "/apis/metrics.k8s.io/v1"+path)
	}
	if err != nil {
		return nil
	}
	return parsePodUsage(raw, namespace, pod, time.Now())
}

func parsePodUsage(raw []byte, namespace string, pod kubeObject, now time.Time) *PodUsage {
	var metrics struct {
		Kind       string
		Metadata   struct{ Name, Namespace string }
		Timestamp  time.Time
		Containers []struct {
			Name  string
			Usage map[string]string
		}
	}
	if json.Unmarshal(raw, &metrics) != nil || metrics.Kind != "PodMetrics" ||
		metrics.Metadata.Name != pod.Metadata.Name || metrics.Metadata.Namespace != namespace ||
		pod.Metadata.CreationTimestamp.IsZero() || !metrics.Timestamp.After(pod.Metadata.CreationTimestamp) ||
		now.Sub(metrics.Timestamp) > 2*time.Minute || metrics.Timestamp.Sub(now) > 5*time.Second {
		return nil
	}
	for _, container := range metrics.Containers {
		cpu, memory := container.Usage["cpu"], container.Usage["memory"]
		if container.Name == "app" && usageQuantity.MatchString(cpu) && usageQuantity.MatchString(memory) {
			return &PodUsage{CPU: cpu, Memory: memory, Timestamp: metrics.Timestamp}
		}
	}
	return nil
}

func describeDiagnosis(result *ProjectDiagnosis, deadline bool) {
	result.Severity, result.LikelyCause = "insufficient_data", "No supported cause was established."
	result.Recommendation = "Review verified deployment evidence before proposing any change."
	sample := result.Sample
	switch {
	case sample != nil && slices.Contains(sample.Reasons, "OOMKilled"):
		result.Severity, result.LikelyCause = "high", "Kubernetes recorded an out-of-memory termination."
		result.Recommendation = "Compare observed memory with the application limit and ask an operator to review resource settings."
	case sample != nil && (slices.Contains(sample.Reasons, "ImagePullBackOff") || slices.Contains(sample.Reasons, "ErrImagePull")):
		result.Severity, result.LikelyCause = "high", "Kubernetes could not pull the sampled pod image."
		result.Recommendation = "Verify the image digest and registry access with the project operator."
	case sample != nil && slices.Contains(sample.Reasons, "FailedScheduling"):
		result.Severity, result.LikelyCause = "warning", "Kubernetes reported a scheduling failure."
		result.Recommendation = "Review resource requests and scheduling constraints."
	case sample != nil && (slices.Contains(sample.Reasons, "FailedMount") || slices.Contains(sample.Reasons, "CreateContainerConfigError")):
		result.Severity, result.LikelyCause = "warning", "The sampled pod could not mount a dependency or start with its container configuration."
		result.Recommendation = "Ask the project operator to verify referenced mounts and configuration through the approved workflow."
	case sample != nil && slices.Contains(sample.Reasons, "Unhealthy"):
		result.Severity, result.LikelyCause = "warning", "Kubernetes reported a probe failure for the sampled pod."
		result.Recommendation = "Compare the health probe with the application's expected endpoint and startup time."
	case sample != nil && (sample.LogErrorSignal || slices.Contains(sample.Reasons, "CrashLoopBackOff")):
		result.Severity, result.LikelyCause = "warning", "The sampled application reported a fatal error or entered a restart backoff."
		result.Recommendation = "Review the redacted logs and compare against an approved previous release."
	case deadline:
		result.Severity, result.LikelyCause = "high", "The deployment controller reported a rollout deadline failure."
		result.Recommendation = "Review readiness probes and the latest verified pod evidence."
	case result.Available != nil && result.Desired != nil && *result.Available < *result.Desired:
		result.Severity, result.LikelyCause = "warning", "Available replicas are below the desired count; cause unverified."
	case result.Available != nil && result.Desired != nil && *result.Desired > 0 && *result.Available >= *result.Desired:
		result.Severity, result.LikelyCause = "info", "The deployment controller reports the desired replicas available."
	}
}
