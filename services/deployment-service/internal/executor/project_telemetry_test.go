package executor

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

func TestProjectLogsVerifyOwnershipAndBoundOutput(t *testing.T) {
	d := model.Deployment{ID: uuid.New(), ProjectID: uuid.New(), Environment: "staging",
		Image: "ghcr.io/cloudforge/api:v1", GitCommitSHA: "abc1234"}
	d.Namespace = "cf-" + d.ProjectID.String()
	getter := &mockDeploymentGetter{getByIDFunc: func(context.Context, uuid.UUID) (model.Deployment, error) {
		return d, nil
	}}
	object := func(kind, name string) kubeObject {
		var item kubeObject
		item.Kind, item.Metadata.Name, item.Metadata.Namespace = kind, name, d.Namespace
		item.Metadata.UID = uuid.NewString()
		item.Metadata.Labels = map[string]string{"cloudforge.ai/project-id": d.ProjectID.String(), "cloudforge.ai/environment": d.Environment}
		return item
	}
	workload := object("Deployment", sanitizeWorkloadName(d))
	workload.Metadata.Annotations = map[string]string{"cloudforge.ai/deployment-id": d.ID.String()}
	replicas := object("ReplicaSet", "app-replicas")
	replicas.Metadata.OwnerReferences = []kubeOwner{{Kind: "Deployment", Name: workload.Metadata.Name, UID: workload.Metadata.UID, Controller: true}}
	pod := object("Pod", "app-pod")
	pod.Spec.Containers = append(pod.Spec.Containers, struct{ Name, Image string }{"app", d.Image})
	pod.Metadata.Annotations = map[string]string{"cloudforge.ai/revision-id": d.ID.String()}
	pod.Metadata.OwnerReferences = []kubeOwner{{Kind: "ReplicaSet", Name: replicas.Metadata.Name, UID: replicas.Metadata.UID, Controller: true}}

	for _, scenario := range []string{"valid", "foreign namespace", "foreign project", "forged owner", "reused pod name"} {
		t.Run(scenario, func(t *testing.T) {
			candidate, refreshed := pod, pod
			switch scenario {
			case "foreign namespace":
				candidate.Metadata.Namespace = "cf-" + uuid.NewString()
			case "foreign project":
				candidate.Metadata.Labels = map[string]string{"cloudforge.ai/project-id": uuid.NewString(), "cloudforge.ai/environment": d.Environment}
			case "forged owner":
				candidate.Metadata.OwnerReferences = []kubeOwner{{Kind: "ReplicaSet", Name: replicas.Metadata.Name, UID: uuid.NewString(), Controller: true}}
			case "reused pod name":
				refreshed.Metadata.UID = uuid.NewString()
			}
			logCalls := 0
			exec := NewKubernetesExecutorWithRunner(getter, "kubectl", time.Second,
				func(_ context.Context, _ []byte, _ string, args ...string) ([]byte, error) {
					switch args[0] + " " + args[1] {
					case "get deployment":
						return json.Marshal(workload)
					case "get replicasets,pods":
						return json.Marshal(map[string][]kubeObject{"items": {replicas, candidate}})
					case "get pod":
						return json.Marshal(refreshed)
					default:
						logCalls++
						for _, flag := range []string{"logs app-pod -c app", "--tail=2", "--limit-bytes=16384", "--since=15m", "-n " + d.Namespace} {
							if !strings.Contains(strings.Join(args, " "), flag) {
								t.Fatalf("missing log constraint %q", flag)
							}
						}
						return []byte("ready\npassword=value\nthird"), nil
					}
				})
			got, err := exec.ProjectLogs(context.Background(), d.ID, 0, 2)
			switch scenario {
			case "valid":
				if err != nil || logCalls != 1 || strings.Join(got.Lines, ",") != "ready,[redacted]" {
					t.Fatalf("unexpected logs: %v, %v", got, err)
				}
			case "reused pod name":
				if !errors.Is(err, ErrTelemetryUnavailable) || len(got.Lines) != 0 {
					t.Fatal("replaced pod logs were disclosed")
				}
			default:
				if logCalls != 0 || len(got.Lines) != 0 {
					t.Fatal("requested logs for an unverified pod")
				}
			}
		})
	}
}

func TestPodRestartsRequiresVerifiedLabels(t *testing.T) {
	var pod kubeObject
	pod.Metadata.UID = "verified-id"
	pod.Metadata.Name = "verified-pod"
	const response = `{"status":"success","data":{"resultType":"vector","result":[{"metric":{
		"__name__":"kube_pod_container_status_restarts_total","pod":"verified-pod","uid":"verified-id",
		"container":"app","namespace":"verified-namespace"},"value":[1000,"0"]}]}}`
	now := time.Unix(1000, 0)
	got := parsePodRestarts(strings.NewReader(response), "verified-namespace", pod, now)
	if got == nil || *got != 0 {
		t.Fatal("verified zero count was unavailable")
	}
	for _, selector := range []string{"verified-namespace", "verified-id", "verified-pod", "app", "kube_pod_container_status_restarts_total", "1000"} {
		unverified := strings.Replace(response, selector, "9000", 1)
		if parsePodRestarts(strings.NewReader(unverified), "verified-namespace", pod, now) != nil {
			t.Fatalf("accepted an invalid metric field %q", selector)
		}
	}
}
