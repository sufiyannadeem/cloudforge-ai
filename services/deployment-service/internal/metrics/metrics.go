package metrics

import (
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

type Metrics struct {
	RequestsTotal *prometheus.CounterVec

	RequestDuration *prometheus.HistogramVec

	RequestsInFlight prometheus.Gauge
}

func New() *Metrics {
	return &Metrics{
		RequestsTotal: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "http_requests_total",
				Help: "Total number of HTTP requests.",
			},
			[]string{
				"method",
				"route",
				"status",
			},
		),

		RequestDuration: prometheus.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "http_request_duration_seconds",
				Help:    "HTTP request duration in seconds.",
				Buckets: prometheus.DefBuckets,
			},
			[]string{
				"method",
				"route",
			},
		),

		RequestsInFlight: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "http_requests_in_flight",
				Help: "Number of HTTP requests currently in flight.",
			},
		),
	}
}

func (m *Metrics) Register(
	registry *prometheus.Registry,
) error {
	collectors := []prometheus.Collector{
		m.RequestsTotal,
		m.RequestDuration,
		m.RequestsInFlight,
	}

	for _, collector := range collectors {
		if err := registry.Register(collector); err != nil {
			return err
		}
	}

	return nil
}

func (m *Metrics) ObserveRequest(
	method string,
	route string,
	status int,
	duration time.Duration,
) {
	m.RequestsTotal.WithLabelValues(
		method,
		route,
		strconv.Itoa(status),
	).Inc()

	m.RequestDuration.WithLabelValues(
		method,
		route,
	).Observe(duration.Seconds())
}
