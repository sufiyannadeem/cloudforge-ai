package metrics

import (
	"context"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/model"
)

type EvidenceInventory interface {
	ListTelemetryDeployments(context.Context) ([]model.Deployment, error)
}
type EvidenceSource interface {
	TrustedProjectEvidence(context.Context, uuid.UUID) (executor.TrustedEvidence, error)
}
type ProjectEvidenceCollector struct {
	inventory EvidenceInventory
	source    EvidenceSource
	mu        sync.RWMutex
	snapshots []executor.TrustedEvidence
	expected  map[string]int
	updated   time.Time
}

func NewProjectEvidenceCollector(inventory EvidenceInventory, source EvidenceSource) *ProjectEvidenceCollector {
	return &ProjectEvidenceCollector{inventory: inventory, source: source}
}
func (c *ProjectEvidenceCollector) Describe(ch chan<- *prometheus.Desc) {
	prometheus.DescribeByCollect(c, ch)
}
func (c *ProjectEvidenceCollector) Refresh(ctx context.Context) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	items, err := c.inventory.ListTelemetryDeployments(ctx)
	expected := map[string]int{}
	snapshots := []executor.TrustedEvidence{}
	if err == nil && len(items) <= 20 {
		for _, d := range items {
			expected[d.ProjectID.String()]++
		}
		for _, d := range items {
			sample, err := c.source.TrustedProjectEvidence(ctx, d.ID)
			if err != nil || sample.ResourceID != d.ID.String() || sample.ProjectID != d.ProjectID.String() || sample.Namespace != d.Namespace {
				continue
			}
			if sample.ObservedAt.After(time.Now()) || time.Since(sample.ObservedAt) > 60*time.Second {
				continue
			}
			snapshots = append(snapshots, sample)
		}
	}
	// Ambiguity invalidates every claimant, not merely the later row.
	counts := map[string]int{}
	for _, sample := range snapshots {
		counts[sample.Cluster+":"+sample.UID]++
	}
	clean := []executor.TrustedEvidence{}
	for _, sample := range snapshots {
		if counts[sample.Cluster+":"+sample.UID] == 1 {
			clean = append(clean, sample)
		}
	}
	c.mu.Lock()
	c.snapshots = clean
	c.expected = expected
	c.updated = time.Now()
	c.mu.Unlock()
}
func (c *ProjectEvidenceCollector) Run(ctx context.Context) {
	c.Refresh(ctx)
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			c.Refresh(ctx)
		}
	}
}
func (c *ProjectEvidenceCollector) Collect(ch chan<- prometheus.Metric) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.updated.IsZero() || time.Since(c.updated) > 60*time.Second {
		return
	}
	emit := func(name string, value float64, names, values []string) {
		ch <- prometheus.MustNewConstMetric(prometheus.NewDesc(name, "Verified internal project evidence.", names, nil), prometheus.GaugeValue, value, values...)
	}
	for project, count := range c.expected {
		emit("cloudforge_project_expected_resources", float64(count), []string{"project_id"}, []string{project})
	}
	for _, sample := range c.snapshots {
		if time.Since(sample.ObservedAt) > 60*time.Second {
			continue
		}
		names := []string{"cluster", "namespace", "uid", "resource_id"}
		values := []string{sample.Cluster, sample.Namespace, sample.UID, sample.ResourceID}
		emit("cloudforge_resource_project_info", 1, append(append([]string{}, names...), "project_id"), append(append([]string{}, values...), sample.ProjectID))
		emit("cloudforge_resource_mapping_timestamp_seconds", float64(sample.ObservedAt.Unix()), names, values)
		for _, uid := range sample.PodUIDs {
			emit("cloudforge_pod_project_info", 1, []string{"cluster", "namespace", "uid", "resource_id", "project_id"}, []string{sample.Cluster, sample.Namespace, uid, sample.ResourceID, sample.ProjectID})
		}
		for signal, observation := range sample.Signals {
			if observation.State != 0 && observation.State != 1 {
				continue
			}
			n := append(append([]string{}, names...), "signal")
			v := append(append([]string{}, values...), signal)
			emit("cloudforge_resource_signal_state", observation.State, n, v)
			emit("cloudforge_resource_signal_observed_timestamp_seconds", float64(observation.ObservedAt.Unix()), n, v)
		}
	}
}
