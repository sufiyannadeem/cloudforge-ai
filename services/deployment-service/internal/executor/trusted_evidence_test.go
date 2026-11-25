package executor

import (
	"context"
	"encoding/json"
	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"strings"
	"testing"
	"time"
)

func TestTrustedEvidenceProjection(t *testing.T) {
	for _, scenario := range []string{"valid", "missing limit", "stale metrics", "wrong revision", "reused UID", "ambiguous owner"} {
		t.Run(scenario, func(t *testing.T) {
			d := model.Deployment{ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging", Image: "ghcr.io/cloudforge/app:v1", GitCommitSHA: "abc1234", ExecutionMode: "kubernetes"}
			d.Namespace = "cf-" + d.ProjectID.String()
			now := time.Now().UTC()
			workUID, rsUID, podUID := uuid.NewString(), uuid.NewString(), uuid.NewString()
			meta := func(name, id string) map[string]any {
				return map[string]any{"name": name, "namespace": d.Namespace, "uid": id, "creationTimestamp": now.Add(-time.Hour).Format(time.RFC3339Nano), "labels": map[string]string{"cloudforge.ai/project-id": d.ProjectID.String(), "cloudforge.ai/environment": d.Environment}}
			}
			owner := func(kind, name, id string) map[string]any {
				return map[string]any{"kind": kind, "name": name, "uid": id, "controller": true}
			}
			wm := meta(sanitizeWorkloadName(d), workUID)
			wm["generation"] = 1
			wm["annotations"] = map[string]string{"cloudforge.ai/deployment-id": d.ID.String()}
			if scenario == "wrong revision" {
				wm["annotations"] = map[string]string{"cloudforge.ai/deployment-id": uuid.NewString()}
			}
			work := map[string]any{"kind": "Deployment", "metadata": wm, "spec": map[string]int{"replicas": 1}, "status": map[string]int{"observedGeneration": 1, "availableReplicas": 1}}
			rm := meta("replicas", rsUID)
			rm["ownerReferences"] = []any{owner("Deployment", sanitizeWorkloadName(d), workUID)}
			rs := map[string]any{"kind": "ReplicaSet", "metadata": rm}
			pm := meta("app-pod", podUID)
			pm["annotations"] = map[string]string{"cloudforge.ai/revision-id": d.ID.String()}
			pm["ownerReferences"] = []any{owner("ReplicaSet", "replicas", rsUID)}
			if scenario == "ambiguous owner" {
				pm["ownerReferences"] = []any{owner("ReplicaSet", "replicas", rsUID), owner("ReplicaSet", "foreign", uuid.NewString())}
			}
			limits := map[string]string{"cpu": "1", "memory": "128Mi"}
			if scenario == "missing limit" {
				limits = map[string]string{}
			}
			pod := map[string]any{"kind": "Pod", "metadata": pm, "spec": map[string]any{"containers": []any{map[string]any{"name": "app", "image": d.Image, "resources": map[string]any{"limits": limits}}}}, "status": map[string]any{"containerStatuses": []any{map[string]any{"name": "app", "ready": false, "restartCount": 4, "state": map[string]any{"waiting": map[string]string{"reason": "CrashLoopBackOff"}}, "lastState": map[string]any{"terminated": map[string]any{"reason": "OOMKilled", "finishedAt": now.Add(-time.Minute).Format(time.RFC3339Nano)}}}}}}
			stamp := now.Add(-time.Second * 5)
			if scenario == "stale metrics" {
				stamp = now.Add(-time.Minute * 5)
			}
			usage := map[string]any{"kind": "PodMetrics", "metadata": map[string]string{"name": "app-pod", "namespace": d.Namespace}, "timestamp": stamp.Format(time.RFC3339Nano), "containers": []any{map[string]any{"name": "app", "usage": map[string]string{"cpu": "950m", "memory": "120Mi"}}}}
			k := &KubernetesExecutor{deploymentGetter: &mockDeploymentGetter{getByIDFunc: func(context.Context, uuid.UUID) (model.Deployment, error) { return d, nil }}, clusterName: "trusted", configured: true}
			reads := 0
			k.runner = func(ctx context.Context, input []byte, command string, args ...string) ([]byte, error) {
				text := strings.Join(args, " ")
				var result any
				switch {
				case strings.HasPrefix(text, "get deployment "):
					result = work
				case strings.HasPrefix(text, "get replicasets,pods "):
					result = map[string]any{"items": []any{rs, pod}}
				case strings.HasPrefix(text, "get --raw "):
					result = usage
				case strings.HasPrefix(text, "get pod "):
					reads++
					if scenario == "reused UID" && reads >= 2 {
						pm["uid"] = uuid.NewString()
					}
					result = pod
				default:
					t.Fatalf("unexpected tool/read: %s", text)
				}
				return json.Marshal(result)
			}
			result, err := k.TrustedProjectEvidence(context.Background(), d.ID)
			if scenario == "wrong revision" || scenario == "reused UID" {
				if err == nil {
					t.Fatal("unverified binding accepted")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if result.ProjectID != d.ProjectID.String() || result.ResourceID != d.ID.String() {
				t.Fatal("ownership not from database")
			}
			if scenario == "valid" {
				for _, signal := range []string{"cpu_pressure", "memory_pressure", "oom", "restart_loop"} {
					if result.Signals[signal].State != 1 {
						t.Fatal(signal)
					}
				}
			} else {
				if _, ok := result.Signals["cpu_pressure"]; ok {
					t.Fatal("fabricated pressure from missing/stale/ambiguous evidence")
				}
			}
		})
	}
}
func TestTrustedQuantity(t *testing.T) {
	for _, raw := range []string{"secret", "NaN", "+Inf", "-1", "1e9", ""} {
		if _, ok := quantity(raw); ok {
			t.Fatal(raw)
		}
	}
	if value, ok := quantity("500m"); !ok || value != .5 {
		t.Fatal("quantity")
	}
}
