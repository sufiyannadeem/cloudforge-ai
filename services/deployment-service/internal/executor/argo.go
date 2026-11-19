package executor

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

var ErrRolloutUnavailable = errors.New("verified Argo Rollout unavailable; check controller, CRDs, namespace RBAC and baseline migration")

// Argo manages progression, analysis, abort and stable ReplicaSet restoration.
// This service only renders a bounded policy, observes it and approves promotion.
type argoObject struct {
	Kind     string
	Metadata struct {
		Name, Namespace, UID, ResourceVersion string
		Generation                            int64
		Labels, Annotations                   map[string]string
		DeletionTimestamp                     *string
	}
	Spec struct {
		Replicas int
		Strategy struct {
			BlueGreen *struct {
				ActiveService, PreviewService string
				AutoPromotionEnabled          *bool
			}
			Canary *struct {
				StableService, CanaryService string
				TrafficRouting               json.RawMessage
			}
		}
		Template struct {
			Spec struct {
				Containers []struct{ Name, Image string }
			}
		}
	}
	Status struct {
		Phase                    string
		ObservedGeneration       string
		CurrentPodHash, StableRS string
		Abort                    bool
		BlueGreen                struct{ ActiveSelector, PreviewSelector string }
		PauseConditions          []struct{ Reason string }
	}
}

type RolloutState struct {
	UID               string `json:"uid"`
	ResourceVersion   string `json:"resource_version"`
	Phase             string `json:"phase"`
	PreviewService    string `json:"preview_service"`
	PreviewReady      bool   `json:"preview_ready"`
	PromotionRequired bool   `json:"promotion_required"`
	TrafficMode       string `json:"traffic_mode"`
}

func (k *KubernetesExecutor) readArgo(ctx context.Context, d model.Deployment) (argoObject, error) {
	var object argoObject
	data, err := k.readScoped(ctx, d.Namespace, "get", "rollouts.argoproj.io", sanitizeWorkloadName(d), "-o", "json")
	if err != nil || json.Unmarshal(data, &object) != nil || object.Kind != "Rollout" ||
		object.Metadata.Name != sanitizeWorkloadName(d) || object.Metadata.Namespace != d.Namespace || object.Metadata.DeletionTimestamp != nil ||
		object.Metadata.UID == "" || object.Metadata.ResourceVersion == "" || object.Metadata.Generation <= 0 ||
		object.Metadata.Labels["cloudforge.ai/project-id"] != d.ProjectID.String() || object.Metadata.Labels["cloudforge.ai/environment"] != d.Environment {
		return object, ErrRolloutUnavailable
	}
	return object, nil
}

func argoMatches(object argoObject, d model.Deployment) bool {
	if object.Metadata.Annotations["cloudforge.ai/deployment-id"] != d.ID.String() {
		return false
	}
	for _, c := range object.Spec.Template.Spec.Containers {
		if c.Name == "app" && c.Image == d.Image {
			return true
		}
	}
	return false
}
func basicCanary(object argoObject) bool {
	strategy := object.Spec.Strategy.Canary
	return strategy != nil && strategy.StableService == "" && strategy.CanaryService == "" && (len(strategy.TrafficRouting) == 0 || string(strategy.TrafficRouting) == "null")
}

func argoObserved(object argoObject) bool {
	return object.Status.ObservedGeneration == strconv.FormatInt(object.Metadata.Generation, 10)
}

func (k *KubernetesExecutor) RolloutState(ctx context.Context, id uuid.UUID) (RolloutState, error) {
	d, err := k.deploymentGetter.GetByID(ctx, id)
	if err != nil || !k.argoEnabled || !d.Strategy.Progressive() || validateDeploymentForExecution(d) != nil {
		return RolloutState{}, ErrRolloutUnavailable
	}
	object, err := k.readArgo(ctx, d)
	if err != nil || !argoMatches(object, d) || !argoObserved(object) {
		return RolloutState{}, ErrRolloutUnavailable
	}
	if object.Status.Phase == "Healthy" {
		stable := object.Status.StableRS
		if d.Strategy.Type == "blue-green" {
			stable = object.Status.BlueGreen.ActiveSelector
		}
		if stable == "" || stable != object.Status.CurrentPodHash {
			return RolloutState{}, ErrRolloutUnavailable
		}
	}
	if d.Strategy.Type == "canary" && !basicCanary(object) {
		return RolloutState{}, ErrRolloutUnavailable
	}
	state := RolloutState{UID: object.Metadata.UID, ResourceVersion: object.Metadata.ResourceVersion, Phase: object.Status.Phase, TrafficMode: "replica-based; no weighted traffic router"}
	if object.Status.Abort {
		state.Phase = "Degraded"
	}
	if d.Strategy.Type == "blue-green" {
		state.TrafficMode = "active/preview services"
		if object.Spec.Strategy.BlueGreen == nil || (object.Spec.Strategy.BlueGreen.AutoPromotionEnabled == nil || *object.Spec.Strategy.BlueGreen.AutoPromotionEnabled) || object.Spec.Strategy.BlueGreen.ActiveService != sanitizeWorkloadName(d) || object.Spec.Strategy.BlueGreen.PreviewService != sanitizeWorkloadName(d)+"-preview" {
			return state, ErrRolloutUnavailable
		}
		state.PreviewService = object.Spec.Strategy.BlueGreen.PreviewService
		for _, pause := range object.Status.PauseConditions {
			if pause.Reason == "BlueGreenPause" {
				state.PromotionRequired = true
			}
		}
	}
	_, workload, pods, err := k.scopedPods(ctx, id)
	if err == nil && workload.Spec.Replicas != nil && *workload.Spec.Replicas > 0 && len(pods) >= *workload.Spec.Replicas {
		state.PreviewReady = true
		for _, pod := range pods {
			ready := false
			for _, c := range pod.Status.ContainerStatuses {
				if c.Name == "app" && c.Ready != nil && *c.Ready {
					ready = true
				}
			}
			podReady := false
			for _, condition := range pod.Status.Conditions {
				if condition.Type == "Ready" && condition.Status == "True" {
					podReady = true
				}
			}
			if !ready || !podReady {
				state.PreviewReady = false
			}
		}
	}
	if state.PreviewReady && d.Strategy.Type == "blue-green" {
		raw, err := k.readScoped(ctx, d.Namespace, "get", "service", state.PreviewService, "-o", "json")
		var preview struct {
			Spec struct{ Selector map[string]string }
		}
		if err != nil || json.Unmarshal(raw, &preview) != nil || preview.Spec.Selector["rollouts-pod-template-hash"] != object.Status.CurrentPodHash {
			state.PreviewReady = false
		}
	}
	return state, nil
}

func (k *KubernetesExecutor) prepareArgo(ctx context.Context, d model.Deployment) (argoObject, error) {
	if !k.argoEnabled {
		return argoObject{}, ErrRolloutUnavailable
	}
	// Never overlap native and Argo controllers over the same selectors/services.
	data, err := k.readScoped(ctx, d.Namespace, "get", "deployment", sanitizeWorkloadName(d), "--ignore-not-found", "-o", "json")
	if err != nil || len(strings.TrimSpace(string(data))) != 0 {
		return argoObject{}, fmt.Errorf("%w: native Deployment must be migrated independently", ErrRolloutUnavailable)
	}
	previous, err := k.readArgo(ctx, d)
	if err != nil || !argoObserved(previous) || (previous.Status.Phase != "Healthy" && previous.Status.Phase != "Degraded") {
		return argoObject{}, fmt.Errorf("%w: an observed healthy stable ReplicaSet is required; initial releases skip progressive gates", ErrRolloutUnavailable)
	}
	currentID, err := uuid.Parse(previous.Metadata.Annotations["cloudforge.ai/deployment-id"])
	if err != nil || currentID == d.ID {
		return argoObject{}, ErrRolloutUnavailable
	}
	current, err := k.deploymentGetter.GetByID(ctx, currentID)
	if err != nil || (current.Status != model.DeploymentStatusSucceeded && current.Status != model.DeploymentStatusFailed) {
		return argoObject{}, ErrRolloutUnavailable
	}
	stableHash := previous.Status.StableRS
	if d.Strategy.Type == "blue-green" {
		stableHash = previous.Status.BlueGreen.ActiveSelector
	}
	if !dns1123LabelRegex.MatchString(stableHash) {
		return argoObject{}, ErrRolloutUnavailable
	}
	data, err = k.readScoped(ctx, d.Namespace, "get", "replicasets", "-l", "rollouts-pod-template-hash="+stableHash, "-o", "json")
	var sets struct {
		Items []struct {
			Metadata struct {
				Namespace       string
				Labels          map[string]string
				OwnerReferences []kubeOwner
			}
			Spec struct {
				Replicas int
				Template struct {
					Metadata struct{ Annotations map[string]string }
					Spec     struct {
						Containers []struct{ Name, Image string }
					}
				}
			}
			Status struct{ ReadyReplicas int }
		}
	}
	if err != nil || json.Unmarshal(data, &sets) != nil || len(sets.Items) != 1 {
		return argoObject{}, ErrRolloutUnavailable
	}
	stable := sets.Items[0]
	owned := false
	for _, owner := range stable.Metadata.OwnerReferences {
		if owner.Controller && owner.Kind == "Rollout" && owner.UID == previous.Metadata.UID && owner.Name == previous.Metadata.Name {
			owned = true
		}
	}
	if !owned || stable.Metadata.Namespace != d.Namespace || stable.Metadata.Labels["cloudforge.ai/project-id"] != d.ProjectID.String() || stable.Metadata.Labels["cloudforge.ai/environment"] != d.Environment || stable.Spec.Replicas < 1 || stable.Status.ReadyReplicas < stable.Spec.Replicas {
		return argoObject{}, ErrRolloutUnavailable
	}
	baselineID, err := uuid.Parse(stable.Spec.Template.Metadata.Annotations["cloudforge.ai/revision-id"])
	if err != nil {
		return argoObject{}, ErrRolloutUnavailable
	}
	baseline, err := k.deploymentGetter.GetByID(ctx, baselineID)
	if err != nil || baseline.Status != model.DeploymentStatusSucceeded || baseline.ExecutionMode != "kubernetes" || baseline.ProjectID != d.ProjectID || baseline.Namespace != d.Namespace || baseline.Environment != d.Environment {
		return argoObject{}, ErrRolloutUnavailable
	}
	imageMatches := false
	for _, c := range stable.Spec.Template.Spec.Containers {
		if c.Name == "app" && c.Image == baseline.Image {
			imageMatches = true
		}
	}
	if !imageMatches || !regexp.MustCompile(`@sha256:[a-f0-9]{64}$`).MatchString(baseline.Image) {
		return argoObject{}, ErrRolloutUnavailable
	}
	data, err = k.readScoped(ctx, d.Namespace, "get", "service", sanitizeWorkloadName(d), "-o", "json")
	var service struct {
		Metadata struct {
			Name, Namespace string
			Labels          map[string]string
		}
		Spec struct {
			Type     string
			Selector map[string]string
			Ports    []struct{ Port, TargetPort int }
		}
	}
	if err != nil || json.Unmarshal(data, &service) != nil || service.Metadata.Name != sanitizeWorkloadName(d) || service.Metadata.Namespace != d.Namespace || service.Metadata.Labels["cloudforge.ai/environment"] != d.Environment || service.Spec.Type != "ClusterIP" || service.Spec.Selector["app.kubernetes.io/name"] != sanitizeWorkloadName(d) || len(service.Spec.Ports) != 1 || service.Spec.Ports[0].Port != 80 || service.Spec.Ports[0].TargetPort != 8080 {
		return argoObject{}, ErrRolloutUnavailable
	}
	if d.Strategy.Type == "blue-green" && (len(service.Spec.Selector) != 2 || service.Spec.Selector["rollouts-pod-template-hash"] != stableHash) {
		return argoObject{}, ErrRolloutUnavailable
	}
	if d.Strategy.Type == "canary" && len(service.Spec.Selector) != 1 {
		return argoObject{}, fmt.Errorf("%w: basic canary requires a shared Service selector without a stable hash", ErrRolloutUnavailable)
	}
	if d.Strategy.Type == "canary" {
		if !basicCanary(previous) {
			return argoObject{}, fmt.Errorf("%w: externally configured traffic routers or hash-pinned canary services require separate integration", ErrRolloutUnavailable)
		}
		if !dns1123LabelRegex.MatchString(k.analysisTemplate) {
			return argoObject{}, fmt.Errorf("%w: approved Prometheus AnalysisTemplate required", ErrRolloutUnavailable)
		}
		data, err := k.readScoped(ctx, d.Namespace, "get", "analysistemplates.argoproj.io", k.analysisTemplate, "-o", "json")
		var template struct {
			Metadata struct{ Annotations map[string]string }
			Kind     string
			Spec     struct {
				Templates []json.RawMessage
				DryRun    []json.RawMessage
				Metrics   []struct {
					Provider                           map[string]json.RawMessage
					SuccessCondition, FailureCondition string
				}
			}
		}
		if err != nil || json.Unmarshal(data, &template) != nil || template.Kind != "AnalysisTemplate" || len(template.Spec.Templates) > 0 || len(template.Spec.DryRun) > 0 || template.Metadata.Annotations["cloudforge.ai/evidence-verified"] != "true" || len(template.Spec.Metrics) == 0 {
			return argoObject{}, ErrRolloutUnavailable
		}
		for _, metric := range template.Spec.Metrics {
			if len(metric.Provider) != 1 || metric.Provider["prometheus"] == nil || metric.SuccessCondition == "" || metric.FailureCondition == "" {
				return argoObject{}, fmt.Errorf("%w: only approved fail-closed Prometheus analysis is supported", ErrRolloutUnavailable)
			}
		}
	}
	return previous, nil
}

func (k *KubernetesExecutor) argoManifest(d model.Deployment) string {
	name := sanitizeWorkloadName(d)
	baseDeployment := d
	baseDeployment.Strategy = model.DeploymentStrategy{ReadinessGates: d.Strategy.ReadinessGates}
	base := generateKubernetesManifest(baseDeployment, name, 600)
	parts := strings.SplitN(base, "---", 2)
	workload := strings.Replace(parts[0], "apiVersion: apps/v1\nkind: Deployment", "apiVersion: argoproj.io/v1alpha1\nkind: Rollout", 1)
	rolling := "  strategy:\n    type: RollingUpdate\n    rollingUpdate:\n      maxSurge: 1\n      maxUnavailable: 0\n"
	strategy := fmt.Sprintf("  progressDeadlineAbort: true\n  strategy:\n    blueGreen:\n      activeService: %s\n      previewService: %s-preview\n      autoPromotionEnabled: false\n      scaleDownDelaySeconds: 30\n", name, name)
	if d.Strategy.Type == "canary" {
		strategy = "  progressDeadlineAbort: true\n  strategy:\n    canary:\n      maxSurge: 1\n      maxUnavailable: 0\n      steps:\n"
		for _, weight := range []int{20, 50, 100} {
			strategy += fmt.Sprintf("      - setWeight: %d\n      - pause: {duration: 60s}\n      - analysis:\n          templates:\n          - templateName: %s\n          args:\n          - name: namespace\n            value: %s\n          - name: revision\n            valueFrom:\n              podTemplateHashValue: Latest\n", weight, k.analysisTemplate, d.Namespace)
		}
	}
	workload = strings.Replace(workload, rolling, strategy, 1)
	// Do not reapply the active Service: Argo owns its hash selector. Resetting it
	// could send traffic to an unapproved revision before promotion.
	preview := strings.Replace(parts[1], "  name: "+name+"\n", "  name: "+name+"-preview\n", 1)
	if d.Strategy.Type == "canary" {
		return workload
	}
	return workload + "---" + preview
}

func (k *KubernetesExecutor) waitArgo(ctx context.Context, id uuid.UUID) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Minute)
	defer cancel()
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		state, err := k.RolloutState(ctx, id)
		if err == nil {
			switch state.Phase {
			case "Degraded", "Error":
				return errors.New("Argo aborted or failed analysis; verify stable revision restoration before retry")
			case "Healthy":
				if state.PreviewReady && !state.PromotionRequired {
					return nil
				}
			}
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("Argo result unconfirmed; manual reconciliation required: %w", ctx.Err())
		case <-ticker.C:
		}
	}
}

// RecoverProgressive observes controller state after a worker restart; never reapplies.
func (k *KubernetesExecutor) RecoverProgressive(ctx context.Context, id uuid.UUID) (bool, error) {
	d, err := k.deploymentGetter.GetByID(ctx, id)
	if err != nil {
		return true, err
	}
	if !d.Strategy.Progressive() {
		return false, nil
	}
	if !k.argoEnabled {
		return true, ErrRolloutUnavailable
	}
	return true, k.waitArgo(ctx, id)
}

// Promote uses the same status operation as Argo's promote command, but with
// atomic UID/resourceVersion/revision tests. It never uses promoteFull.
func (k *KubernetesExecutor) Promote(ctx context.Context, id uuid.UUID, expected RolloutState) error {
	d, err := k.deploymentGetter.GetByID(ctx, id)
	if err != nil || d.Strategy.Type != "blue-green" {
		return ErrRolloutUnavailable
	}
	current, err := k.RolloutState(ctx, id)
	if err != nil || current.UID != expected.UID || current.ResourceVersion != expected.ResourceVersion || !current.PromotionRequired || !current.PreviewReady || current.Phase != "Paused" {
		return ErrRolloutUnavailable
	}
	patch, _ := json.Marshal([]map[string]any{
		{"op": "test", "path": "/metadata/uid", "value": current.UID},
		{"op": "test", "path": "/metadata/resourceVersion", "value": current.ResourceVersion},
		{"op": "test", "path": "/metadata/annotations/cloudforge.ai~1deployment-id", "value": id.String()},
		{"op": "remove", "path": "/status/pauseConditions"},
	})
	_, err = k.readScoped(ctx, d.Namespace, "patch", "rollouts.argoproj.io", sanitizeWorkloadName(d), "--subresource=status", "--type=json", "-p", string(patch))
	return err
}
