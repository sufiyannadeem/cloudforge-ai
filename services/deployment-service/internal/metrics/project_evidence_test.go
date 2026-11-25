package metrics

import (
	"context"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

type evidenceFixture struct {
	items            []model.Deployment
	stale, duplicate bool
}

func (f evidenceFixture) ListTelemetryDeployments(context.Context) ([]model.Deployment, error) {
	return f.items, nil
}
func (f evidenceFixture) TrustedProjectEvidence(ctx context.Context, id uuid.UUID) (executor.TrustedEvidence, error) {
	for _, d := range f.items {
		if d.ID == id {
			stamp := time.Now()
			if f.stale {
				stamp = stamp.Add(-time.Minute * 2)
			}
			uid := id.String()
			if f.duplicate {
				uid = "same-uid"
			}
			return executor.TrustedEvidence{ResourceID: id.String(), ProjectID: d.ProjectID.String(), Cluster: "trusted", Namespace: d.Namespace, UID: uid, ObservedAt: stamp, Signals: map[string]executor.EvidenceObservation{"cpu_pressure": {State: 1, ObservedAt: stamp}}}, nil
		}
	}
	return executor.TrustedEvidence{}, executor.ErrTelemetryUnavailable
}
func TestCollectorFailsClosed(t *testing.T) {
	project := uuid.New()
	items := []model.Deployment{{ID: uuid.New(), ProjectID: project, Namespace: "cf-" + project.String()}, {ID: uuid.New(), ProjectID: project, Namespace: "cf-" + project.String()}}
	for _, scenario := range []string{"valid", "stale", "duplicate", "oversized"} {
		t.Run(scenario, func(t *testing.T) {
			f := evidenceFixture{items: items, stale: scenario == "stale", duplicate: scenario == "duplicate"}
			if scenario == "oversized" {
				f.items = make([]model.Deployment, 21)
			}
			c := NewProjectEvidenceCollector(f, f)
			c.Refresh(context.Background())
			registry := prometheus.NewRegistry()
			registry.MustRegister(c)
			families, err := registry.Gather()
			if err != nil {
				t.Fatal(err)
			}
			found := false
			for _, family := range families {
				if family.GetName() == "cloudforge_resource_project_info" {
					found = true
				}
			}
			if found != (scenario == "valid") {
				t.Fatal("unsafe binding")
			}
			c.updated = time.Now().Add(-time.Minute * 2)
			families, err = registry.Gather()
			if err != nil || len(families) > 0 {
				t.Fatal("stale cache")
			}
		})
	}
}
func TestScrapeRequiresDedicatedIdentity(t *testing.T) {
	path := filepath.Join(t.TempDir(), "token")
	token := "dedicated-monitoring-identity-at-least-32-bytes"
	if err := os.WriteFile(path, []byte(token), 0600); err != nil {
		t.Fatal(err)
	}
	calls := 0
	handler := ProtectEvidenceMetrics(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++; w.WriteHeader(200) }), path)
	for _, auth := range []string{"", "Bearer frontend-key", "Bearer " + token} {
		r := httptest.NewRequest("GET", "/metrics", nil)
		if auth != "" {
			r.Header.Set("Authorization", auth)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		want := 401
		if auth == "Bearer "+token {
			want = 200
		}
		if w.Code != want {
			t.Fatal(w.Code)
		}
	}
	if calls != 1 {
		t.Fatal("unauthorized gather")
	}
}
