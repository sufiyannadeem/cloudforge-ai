package executor

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type argoFixture struct {
	unsafeTemplate                                   bool
	d, baseline                                      model.Deployment
	applied, abort, stale, unready, foreign, missing bool
	router                                           bool
	mutations                                        []string
}

func newArgoFixture(strategy string) *argoFixture {
	d := model.Deployment{ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging", GitCommitSHA: "abcdef1", Image: "ghcr.io/example/app@sha256:" + strings.Repeat("a", 64), Status: model.DeploymentStatusRunning, ExecutionMode: "kubernetes", Strategy: model.DeploymentStrategy{Type: strategy}}
	d.Namespace = "cf-" + d.ProjectID.String()
	baseline := d
	baseline.ID = uuid.New()
	baseline.Image = "ghcr.io/example/app@sha256:" + strings.Repeat("b", 64)
	baseline.Status = model.DeploymentStatusSucceeded
	return &argoFixture{d: d, baseline: baseline}
}
func (f *argoFixture) executor() *KubernetesExecutor {
	getter := &mockDeploymentGetter{getByIDFunc: func(_ context.Context, id uuid.UUID) (model.Deployment, error) {
		if id == f.baseline.ID {
			return f.baseline, nil
		}
		return f.d, nil
	}}
	return NewKubernetesExecutorWithOptions(getter, KubernetesOptions{ArgoEnabled: true, AnalysisTemplate: "cloudforge-release-health"}, f.run)
}
func (f *argoFixture) run(_ context.Context, stdin []byte, _ string, args ...string) ([]byte, error) {
	name := sanitizeWorkloadName(f.d)
	uid := "11111111-1111-1111-1111-111111111111"
	metadata := func(n string) map[string]any {
		return map[string]any{"name": n, "namespace": f.d.Namespace, "uid": uid, "resourceVersion": "42", "generation": 2, "labels": map[string]string{"cloudforge.ai/project-id": f.d.ProjectID.String(), "cloudforge.ai/environment": f.d.Environment}}
	}
	owner := func(kind, n, id string) []map[string]any {
		return []map[string]any{{"kind": kind, "name": n, "uid": id, "controller": true}}
	}
	marshal := func(v any) ([]byte, error) { return json.Marshal(v) }
	switch args[0] + " " + args[1] {
	case "apply -f":
		if !strings.Contains(strings.Join(args, " "), "--server-side") {
			return nil, errors.New("progressive apply must use server preconditions")
		}
		f.applied = true
		f.mutations = append(f.mutations, string(stdin))
		return []byte("applied"), nil
	case "get deployment":
		return nil, nil
	case "get rollouts.argoproj.io":
		if f.missing {
			return nil, errors.New("CRD not installed")
		}
		d := f.baseline
		if f.applied {
			d = f.d
		}
		meta := metadata(name)
		meta["annotations"] = map[string]string{"cloudforge.ai/deployment-id": d.ID.String()}
		if f.foreign {
			meta["namespace"] = "unrelated"
		}
		phase, hash, stable := "Healthy", "old", "old"
		if f.applied {
			hash = "new"
			if f.d.Strategy.Type == "blue-green" {
				phase = "Paused"
			} else {
				stable = "new"
			}
		}
		status := map[string]any{"phase": phase, "observedGeneration": "2", "currentPodHash": hash, "stableRS": stable, "blueGreen": map[string]string{"activeSelector": stable, "previewSelector": hash}}
		if f.stale {
			status["observedGeneration"] = "1"
		}
		if f.abort {
			status["phase"] = "Degraded"
			status["abort"] = true
		}
		if phase == "Paused" {
			status["pauseConditions"] = []map[string]string{{"reason": "BlueGreenPause"}}
		}
		strategy := map[string]any{"canary": map[string]any{}}
		if f.router {
			strategy["canary"] = map[string]any{"trafficRouting": map[string]any{"nginx": map[string]string{"stableIngress": "fixture"}}}
		}
		if f.d.Strategy.Type == "blue-green" {
			strategy = map[string]any{"blueGreen": map[string]any{"activeService": name, "previewService": name + "-preview", "autoPromotionEnabled": false}}
		}
		return marshal(map[string]any{"kind": "Rollout", "metadata": meta, "spec": map[string]any{"replicas": 2, "strategy": strategy, "template": map[string]any{"spec": map[string]any{"containers": []map[string]string{{"name": "app", "image": d.Image}}}}}, "status": status})
	case "get replicasets":
		meta := metadata(name + "-old")
		meta["ownerReferences"] = owner("Rollout", name, uid)
		return marshal(map[string]any{"items": []any{map[string]any{"metadata": meta, "spec": map[string]any{"replicas": 2, "template": map[string]any{"metadata": map[string]any{"annotations": map[string]string{"cloudforge.ai/revision-id": f.baseline.ID.String()}}, "spec": map[string]any{"containers": []map[string]string{{"name": "app", "image": f.baseline.Image}}}}}, "status": map[string]int{"readyReplicas": 2}}}})
	case "get service":
		selector := map[string]string{"app.kubernetes.io/name": name}
		if strings.HasSuffix(args[2], "-preview") {
			selector["rollouts-pod-template-hash"] = "new"
		} else if f.d.Strategy.Type == "blue-green" {
			selector["rollouts-pod-template-hash"] = "old"
		}
		return marshal(map[string]any{"metadata": metadata(args[2]), "spec": map[string]any{"type": "ClusterIP", "selector": selector, "ports": []map[string]int{{"port": 80, "targetPort": 8080}}}})
	case "get analysistemplates.argoproj.io":
		if f.unsafeTemplate {
			return []byte(`{"kind":"AnalysisTemplate","metadata":{"annotations":{"cloudforge.ai/evidence-verified":"true"}},"spec":{"dryRun":[{"metricName":".*"}],"metrics":[{"provider":{"prometheus":{}},"successCondition":"true","failureCondition":"false"}]}}`), nil
		}
		return []byte(`{"kind":"AnalysisTemplate","metadata":{"annotations":{"cloudforge.ai/evidence-verified":"true"}},"spec":{"metrics":[{"provider":{"prometheus":{}},"successCondition":"len(result)==1","failureCondition":"len(result)!=1"}]}}`), nil
	case "get replicasets,pods":
		rsUID := "22222222-2222-2222-2222-222222222222"
		rsMeta := metadata(name + "-new")
		rsMeta["uid"] = rsUID
		rsMeta["ownerReferences"] = owner("Rollout", name, uid)
		items := []any{map[string]any{"kind": "ReplicaSet", "metadata": rsMeta}}
		for _, podName := range []string{"pod-one", "pod-two"} {
			meta := metadata(podName)
			meta["uid"] = uuid.NewString()
			meta["ownerReferences"] = owner("ReplicaSet", name+"-new", rsUID)
			meta["annotations"] = map[string]string{"cloudforge.ai/revision-id": f.d.ID.String()}
			ready := "True"
			if f.unready {
				ready = "False"
			}
			items = append(items, map[string]any{"kind": "Pod", "metadata": meta, "spec": map[string]any{"containers": []map[string]string{{"name": "app", "image": f.d.Image}}}, "status": map[string]any{"conditions": []map[string]string{{"type": "Ready", "status": ready}}, "containerStatuses": []map[string]any{{"name": "app", "ready": true}}}})
		}
		return marshal(map[string]any{"items": items})
	case "patch rollouts.argoproj.io":
		f.mutations = append(f.mutations, strings.Join(args, " "))
		return []byte("patched"), nil
	}
	return nil, errors.New("unexpected fixture command")
}

func TestStrategyManifestsPreserveReadinessAndControllerOwnership(t *testing.T) {
	if strings.Contains(generateKubernetesManifest(model.Deployment{}, "fixture", 1), "progressDeadlineSeconds: 1\n") {
		t.Fatal("progress deadline must exceed the readiness delay")
	}
	f := newArgoFixture("canary")
	k := f.executor()
	manifest := k.argoManifest(f.d)
	if dir := os.Getenv("CLOUDFORGE_MANIFEST_TEST_DIR"); dir != "" {
		if err := os.WriteFile(filepath.Join(dir, "canary.yml"), []byte(manifest), 0600); err != nil {
			t.Fatal(err)
		}
	}
	for _, required := range []string{"kind: Rollout", "progressDeadlineAbort: true", "setWeight: 20", "setWeight: 50", "setWeight: 100", "templateName: cloudforge-release-health", "podTemplateHashValue: Latest", "readinessProbe:", "startupProbe:", "terminationGracePeriodSeconds: 60", "topologyKey: kubernetes.io/hostname", "topologyKey: topology.kubernetes.io/zone", "whenUnsatisfiable: ScheduleAnyway"} {
		if !strings.Contains(manifest, required) {
			t.Fatal(required)
		}
	}
	for _, forbidden := range []string{"trafficRouting:", "kind: Service", "RollingUpdate", "%!"} {
		if strings.Contains(manifest, forbidden) {
			t.Fatal(forbidden)
		}
	}
	f.d.Strategy.Type = "blue-green"
	manifest = k.argoManifest(f.d)
	if dir := os.Getenv("CLOUDFORGE_MANIFEST_TEST_DIR"); dir != "" {
		if err := os.WriteFile(filepath.Join(dir, "blue-green.yml"), []byte(manifest), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if !strings.Contains(manifest, "autoPromotionEnabled: false") || strings.Count(manifest, "kind: Service") != 1 || !strings.Contains(manifest, "name: "+sanitizeWorkloadName(f.d)+"-preview") {
		t.Fatal(manifest)
	}
	f.d.Strategy = model.DeploymentStrategy{Type: "rolling", MaxUnavailable: 1, ReadinessGates: []string{"example.test/Ready"}}
	manifest = generateKubernetesManifest(f.d, "application", 120)
	if !strings.Contains(manifest, "maxSurge: 0\n      maxUnavailable: 1") || !strings.Contains(manifest, "conditionType: example.test/Ready") {
		t.Fatal(manifest)
	}
}
func TestArgoExecutionAndRecoveryNeverFakeHealth(t *testing.T) {
	f := newArgoFixture("canary")
	k := f.executor()
	result, err := k.Execute(context.Background(), f.d.ID)
	if err != nil || result.Status != "succeeded" || len(f.mutations) != 1 {
		t.Fatal(result, err)
	}
	if !strings.Contains(f.mutations[0], "resourceVersion: ") || !strings.Contains(f.mutations[0], "  uid: ") {
		t.Fatal("rollout update lacks object fencing")
	}
	f.mutations = nil
	handled, err := k.RecoverProgressive(context.Background(), f.d.ID)
	if !handled || err != nil || len(f.mutations) != 0 {
		t.Fatal(handled, err, f.mutations)
	}
	for _, scenario := range []string{"abort", "stale", "unready", "missing", "foreign"} {
		t.Run(scenario, func(t *testing.T) {
			f := newArgoFixture("canary")
			f.applied = true
			switch scenario {
			case "abort":
				f.abort = true
			case "stale":
				f.stale = true
			case "unready":
				f.unready = true
			case "missing":
				f.missing = true
			case "foreign":
				f.foreign = true
			}
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Millisecond)
			defer cancel()
			if f.executor().waitArgo(ctx, f.d.ID) == nil {
				t.Fatal("unverified health accepted")
			}
		})
	}
}
func TestArgoPreflightAndFailedLeaseCannotMutate(t *testing.T) {
	for _, scenario := range []string{"missing CRD", "failed claim", "disabled", "unverified baseline", "unsupported router", "dry-run analysis"} {
		t.Run(scenario, func(t *testing.T) {
			f := newArgoFixture("canary")
			k := f.executor()
			if scenario == "missing CRD" {
				f.missing = true
			}
			if scenario == "disabled" {
				k.argoEnabled = false
			}
			if scenario == "unverified baseline" {
				f.baseline.ExecutionMode = "simulated"
			}
			if scenario == "unsupported router" {
				f.router = true
			}
			if scenario == "dry-run analysis" {
				f.unsafeTemplate = true
			}
			claims := 0
			ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
			defer cancel()
			_, err := k.ExecuteWithClaim(ctx, f.d.ID, func() error {
				claims++
				if scenario == "failed claim" {
					return errors.New("lease lost")
				}
				return nil
			})
			expectedClaims := 0
			if scenario == "failed claim" {
				expectedClaims = 1
			}
			if claims != expectedClaims {
				t.Fatalf("preflight did not reject before claim: %d", claims)
			}
			if err == nil || len(f.mutations) != 0 {
				t.Fatal("mutation without prerequisites/ownership", err)
			}
		})
	}
}
func TestBlueGreenPromotionRequiresExactReadyPreview(t *testing.T) {
	for _, scenario := range []string{"valid", "stale version", "unready", "aborted"} {
		t.Run(scenario, func(t *testing.T) {
			f := newArgoFixture("blue-green")
			f.applied = true
			k := f.executor()
			state, err := k.RolloutState(context.Background(), f.d.ID)
			if err != nil {
				t.Fatal(err)
			}
			if !state.PromotionRequired || !state.PreviewReady {
				t.Fatal(state)
			}
			if scenario == "stale version" {
				state.ResourceVersion = "old"
			}
			if scenario == "unready" {
				f.unready = true
			}
			if scenario == "aborted" {
				f.abort = true
			}
			err = k.Promote(context.Background(), f.d.ID, state)
			if scenario != "valid" {
				if err == nil || len(f.mutations) > 0 {
					t.Fatal("unsafe promotion", err)
				}
				return
			}
			if err != nil || len(f.mutations) != 1 {
				t.Fatal(err, f.mutations)
			}
			for _, required := range []string{"/metadata/uid", "/metadata/resourceVersion", "/metadata/annotations/cloudforge.ai~1deployment-id", "--subresource=status"} {
				if !strings.Contains(f.mutations[0], required) {
					t.Fatal(required)
				}
			}
			if !strings.Contains(f.mutations[0], `"op":"remove"`) || !strings.Contains(f.mutations[0], "/status/pauseConditions") {
				t.Fatal("promotion must remove the pause condition without replacing the full status")
			}
			if strings.Contains(f.mutations[0], "promoteFull") {
				t.Fatal("analysis bypass")
			}
		})
	}
}

type progressiveHistoryGetter struct{ *mockDeploymentGetter }

func (g progressiveHistoryGetter) HasProgressiveHistory(context.Context, uuid.UUID) (bool, error) {
	return true, nil
}
func TestNativeCannotHideExistingRolloutByDisablingArgo(t *testing.T) {
	f := newArgoFixture("canary")
	f.d.Strategy = model.DeploymentStrategy{Type: "rolling", MaxSurge: 1}
	mutations := 0
	getter := progressiveHistoryGetter{&mockDeploymentGetter{getByIDFunc: func(context.Context, uuid.UUID) (model.Deployment, error) { return f.d, nil }}}
	k := NewKubernetesExecutorWithOptions(getter, KubernetesOptions{ArgoEnabled: false}, func(_ context.Context, _ []byte, _ string, args ...string) ([]byte, error) {
		if args[0] == "api-resources" {
			return []byte("rollouts.argoproj.io"), nil
		}
		if args[0] == "get" {
			return []byte(`{"kind":"Rollout"}`), nil
		}
		mutations++
		return nil, nil
	})
	if _, err := k.Execute(context.Background(), f.d.ID); err == nil || mutations != 0 {
		t.Fatal("feature flag bypassed workload isolation", err)
	}
}
