package metrics

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

type DeploymentMetrics struct {
	DeploymentsTotal *prometheus.CounterVec

	DeploymentDuration *prometheus.HistogramVec

	DeploymentsInProgress prometheus.Gauge
}

func NewDeploymentMetrics() *DeploymentMetrics {
	return &DeploymentMetrics{
		DeploymentsTotal: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "cloudforge_deployments_total",
				Help: "Total number of deployment executions.",
			},
			[]string{
				"environment",
				"status",
			},
		),

		DeploymentDuration: prometheus.NewHistogramVec(
			prometheus.HistogramOpts{
				Name: "cloudforge_deployment_duration_seconds",
				Help: "Duration of deployment executions in seconds.",
				Buckets: []float64{
					0.1,
					0.5,
					1,
					2,
					5,
					10,
					30,
					60,
					120,
				},
			},
			[]string{
				"environment",
			},
		),

		DeploymentsInProgress: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "cloudforge_deployments_in_progress",
				Help: "Number of deployments currently in progress.",
			},
		),
	}
}

func (m *DeploymentMetrics) Register(
	registry *prometheus.Registry,
) error {
	collectors := []prometheus.Collector{
		m.DeploymentsTotal,
		m.DeploymentDuration,
		m.DeploymentsInProgress,
	}

	for _, collector := range collectors {
		if err := registry.Register(collector); err != nil {
			return err
		}
	}

	return nil
}

func (m *DeploymentMetrics) DeploymentStarted() {
	m.DeploymentsInProgress.Inc()
}

func (m *DeploymentMetrics) DeploymentCompleted(
	environment string,
	status string,
	duration time.Duration,
) {
	m.DeploymentsInProgress.Dec()

	m.DeploymentsTotal.WithLabelValues(
		environment,
		status,
	).Inc()

	m.DeploymentDuration.WithLabelValues(
		environment,
	).Observe(duration.Seconds())
}
