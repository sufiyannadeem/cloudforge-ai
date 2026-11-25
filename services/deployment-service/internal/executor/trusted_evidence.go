package executor

// Internal metrics projection: no logs, event messages, configuration or tools.
import (
	"context"
	"encoding/json"
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

type EvidenceObservation struct {
	State      float64
	ObservedAt time.Time
}
type TrustedEvidence struct {
	ResourceID, ProjectID, Cluster, Namespace, UID string
	PodUIDs                                        []string
	ObservedAt                                     time.Time
	Signals                                        map[string]EvidenceObservation
}

func (k *KubernetesExecutor) TrustedProjectEvidence(ctx context.Context, id uuid.UUID) (TrustedEvidence, error) {
	ctx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	d, workload, pods, err := k.scopedPods(ctx, id)
	if err != nil || d.ExecutionMode != "kubernetes" || len(pods) > 5 || k.clusterName == "" {
		return TrustedEvidence{}, ErrTelemetryUnavailable
	}
	now := time.Now().UTC()
	result := TrustedEvidence{ResourceID: d.ID.String(), ProjectID: d.ProjectID.String(), Cluster: k.clusterName, Namespace: d.Namespace,
		UID: workload.Metadata.UID, ObservedAt: now, Signals: map[string]EvidenceObservation{}}
	// The database establishes ownership; Kubernetes labels are consistency checks,
	// never the source of a project ID. Ambiguous controller/UID chains are rejected.
	seen := map[string]bool{}
	for _, pod := range pods {
		if seen[pod.Metadata.UID] {
			return TrustedEvidence{}, ErrTelemetryUnavailable
		}
		seen[pod.Metadata.UID] = true
		result.PodUIDs = append(result.PodUIDs, pod.Metadata.UID)
	}
	desired := workload.Spec.Replicas
	if desired == nil || *desired <= 0 || workload.Metadata.Generation <= 0 || int64(workload.Status.ObservedGeneration) != workload.Metadata.Generation {
		return result, nil
	}
	degraded := float64(0)
	if workload.Status.AvailableReplicas < 0 {
		return TrustedEvidence{}, ErrTelemetryUnavailable
	}
	if workload.Status.AvailableReplicas < *desired {
		degraded = 1
	}
	readyCount, readyKnown := 0, true
	for _, pod := range pods {
		ready, _, _ := appStatus(pod)
		if ready == nil {
			readyKnown = false
		} else if *ready {
			readyCount++
		}
	}
	if readyKnown && len(pods) >= *desired && readyCount < *desired {
		degraded = 1
	}
	if degraded == 1 || (readyKnown && len(pods) >= *desired) {
		result.Signals["deployment_health"] = EvidenceObservation{degraded, now}
	}
	if len(pods) == 0 || len(pods) < *desired {
		return result, nil
	}
	cpu, memory, oom, loops := float64(0), float64(0), float64(0), float64(0)
	cpuKnown, memoryKnown, oomKnown, loopsKnown := true, true, true, true
	stamp := now
	for _, pod := range pods {
		ready, _, reasons := appStatus(pod)
		appStatuses, currentStateKnown := 0, false
		for _, status := range pod.Status.ContainerStatuses {
			if status.Name == "app" {
				appStatuses++
				currentStateKnown = status.State.Waiting != nil || status.State.Terminated != nil
			}
		}
		if appStatuses > 1 {
			return TrustedEvidence{}, ErrTelemetryUnavailable
		}
		if ready == nil || (!*ready && !currentStateKnown) {
			loopsKnown = false
		}
		for _, condition := range pod.Status.Conditions {
			if condition.Type == "PodScheduled" && condition.Status == "False" && condition.Reason == "Unschedulable" {
				result.Signals["scheduling_failure"] = EvidenceObservation{1, now}
			}
		}
		for _, reason := range reasons {
			if reason == "ImagePullBackOff" || reason == "ErrImagePull" {
				result.Signals["image_pull_failure"] = EvidenceObservation{1, now}
			}
			if reason == "CreateContainerConfigError" {
				result.Signals["startup_configuration"] = EvidenceObservation{1, now}
			}
			if reason == "CrashLoopBackOff" {
				loops = 1
			}
		}
		raw, readErr := k.readScoped(ctx, d.Namespace, "get", "pod", pod.Metadata.Name, "-o", "json")
		var spec struct {
			Metadata struct{ UID, Namespace string }
			Spec     struct {
				Containers []struct {
					Name      string
					Resources struct{ Limits map[string]string }
				}
			}
			Status struct {
				ContainerStatuses []struct {
					Name      string
					LastState struct {
						Terminated *struct {
							Reason     string
							FinishedAt time.Time
						}
					}
				}
			}
		}
		cpuLimit, memoryLimit := float64(0), float64(0)
		if readErr != nil || json.Unmarshal(raw, &spec) != nil || spec.Metadata.UID != pod.Metadata.UID || spec.Metadata.Namespace != d.Namespace {
			return TrustedEvidence{}, ErrTelemetryUnavailable
		}
		appCount := 0
		for _, c := range spec.Spec.Containers {
			if c.Name == "app" {
				appCount++
				cpuLimit, _ = quantity(c.Resources.Limits["cpu"])
				memoryLimit, _ = quantity(c.Resources.Limits["memory"])
			}
		}
		if appCount != 1 {
			return TrustedEvidence{}, ErrTelemetryUnavailable
		}
		recentTermination := false
		for _, c := range spec.Status.ContainerStatuses {
			if c.Name == "app" && c.LastState.Terminated != nil {
				term := c.LastState.Terminated
				if !term.FinishedAt.IsZero() && !term.FinishedAt.After(now) && now.Sub(term.FinishedAt) <= 15*time.Minute {
					recentTermination = true
					if term.Reason == "OOMKilled" {
						oom = 1
					}
				}
			}
		}
		// No recent termination evidence is unknown, not proof that OOM never occurred.
		if !recentTermination {
			oomKnown = false
		}
		usage := k.podUsage(ctx, d.Namespace, pod)
		if usage == nil || usage.Timestamp.After(time.Now()) {
			cpuKnown = false
			memoryKnown = false
		} else {
			if usage.Timestamp.Before(stamp) {
				stamp = usage.Timestamp
			}
			usedCPU, cpuOK := quantity(usage.CPU)
			usedMem, memOK := quantity(usage.Memory)
			if !cpuOK || cpuLimit <= 0 {
				cpuKnown = false
			} else if usedCPU/cpuLimit >= .9 {
				cpu = 1
			}
			if !memOK || memoryLimit <= 0 {
				memoryKnown = false
			} else if usedMem/memoryLimit >= .9 {
				memory = 1
			}
		}
		if !k.podStillOwned(ctx, d, pod) {
			return TrustedEvidence{}, ErrTelemetryUnavailable
		}
	}
	if cpuKnown {
		result.Signals["cpu_pressure"] = EvidenceObservation{cpu, stamp}
	}
	if memoryKnown {
		result.Signals["memory_pressure"] = EvidenceObservation{memory, stamp}
	}
	if oomKnown || oom == 1 {
		result.Signals["oom"] = EvidenceObservation{oom, now}
	}
	if loopsKnown {
		result.Signals["restart_loop"] = EvidenceObservation{loops, now}
	}
	return result, nil
}

func quantity(raw string) (float64, bool) {
	if !usageQuantity.MatchString(raw) {
		return 0, false
	}
	factors := []struct {
		suffix string
		factor float64
	}{{"Ki", 1024}, {"Mi", 1048576}, {"Gi", 1073741824}, {"Ti", 1099511627776}, {"n", 1e-9}, {"u", 1e-6}, {"m", .001}}
	factor := float64(1)
	for _, unit := range factors {
		if strings.HasSuffix(raw, unit.suffix) {
			raw = strings.TrimSuffix(raw, unit.suffix)
			factor = unit.factor
			break
		}
	}
	value, err := strconv.ParseFloat(raw, 64)
	value *= factor
	return value, err == nil && !math.IsNaN(value) && !math.IsInf(value, 0) && value >= 0
}
