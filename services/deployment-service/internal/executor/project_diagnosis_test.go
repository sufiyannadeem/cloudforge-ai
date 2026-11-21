package executor

import (
	"fmt"
	"testing"
	"time"
)

func TestDiagnosisPrioritizesEvidenceAndDoesNotInventPodStatus(t *testing.T) {
	d := ProjectDiagnosis{}
	describeDiagnosis(&d, false)
	if d.Severity != "insufficient_data" {
		t.Fatalf("missing evidence reported %s", d.Severity)
	}
	d.Sample = &PodSample{Reasons: []string{"OOMKilled"}}
	describeDiagnosis(&d, true)
	if d.Severity != "high" || d.LikelyCause != "Kubernetes recorded an out-of-memory termination." {
		t.Fatalf("pod evidence did not ground the diagnosis: %+v", d)
	}
	if got := appendReason(nil, "arbitrary event text"); len(got) != 0 {
		t.Fatal("untrusted event text was accepted as evidence")
	}
}

func TestPodUsageRequiresCurrentVerifiedPodSample(t *testing.T) {
	now := time.Now().UTC()
	pod := kubeObject{}
	pod.Metadata.Name = "pod"
	pod.Metadata.CreationTimestamp = now.Add(-time.Minute)
	data := func(namespace string, offset time.Duration) []byte {
		return []byte(fmt.Sprintf(`{"kind":"PodMetrics","metadata":{"name":"pod","namespace":%q},
		   "timestamp":%q,"containers":[{"name":"app","usage":{"cpu":"25m","memory":"32Mi"}}]}`,
			namespace, now.Add(offset).Format(time.RFC3339Nano)))
	}
	if usage := parsePodUsage(data("project", -time.Second), "project", pod, now); usage == nil || usage.CPU != "25m" {
		t.Fatal("valid usage was unavailable")
	}
	for _, raw := range [][]byte{data("other", -time.Second), data("project", -90*time.Second)} {
		if parsePodUsage(raw, "project", pod, now) != nil {
			t.Fatal("foreign or pre-creation metrics were accepted")
		}
	}
}
