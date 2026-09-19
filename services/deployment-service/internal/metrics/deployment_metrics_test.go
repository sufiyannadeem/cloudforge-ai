package metrics

import (
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestDeploymentMetrics(t *testing.T) {
	metrics := NewDeploymentMetrics()
	registry := prometheus.NewRegistry()

	if err := metrics.Register(registry); err != nil {
		t.Fatalf("failed to register metrics: %v", err)
	}

	metrics.DeploymentStarted()

	inProgress := testutil.ToFloat64(
		metrics.DeploymentsInProgress,
	)

	if inProgress != 1 {
		t.Fatalf(
			"expected one deployment in progress, got %v",
			inProgress,
		)
	}

	metrics.DeploymentCompleted(
		"development",
		"succeeded",
		500*time.Millisecond,
	)

	inProgress = testutil.ToFloat64(
		metrics.DeploymentsInProgress,
	)

	if inProgress != 0 {
		t.Fatalf(
			"expected zero deployments in progress, got %v",
			inProgress,
		)
	}

	total := testutil.ToFloat64(
		metrics.DeploymentsTotal.WithLabelValues(
			"development",
			"succeeded",
		),
	)

	if total != 1 {
		t.Fatalf(
			"expected one successful deployment, got %v",
			total,
		)
	}
}
