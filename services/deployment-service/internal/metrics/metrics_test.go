package metrics

import (
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

func TestNewMetricsRegisterSuccessfully(t *testing.T) {
	t.Parallel()

	serviceMetrics := New()
	registry := prometheus.NewRegistry()

	if err := serviceMetrics.Register(registry); err != nil {
		t.Fatalf(
			"expected metrics registration to succeed, got: %v",
			err,
		)
	}
}

func TestObserveRequestRecordsMetrics(t *testing.T) {
	t.Parallel()

	serviceMetrics := New()
	registry := prometheus.NewRegistry()

	if err := serviceMetrics.Register(registry); err != nil {
		t.Fatalf(
			"expected metrics registration to succeed, got: %v",
			err,
		)
	}

	serviceMetrics.ObserveRequest(
		"GET",
		"/health",
		200,
		25*time.Millisecond,
	)

	families, err := registry.Gather()
	if err != nil {
		t.Fatalf(
			"expected metrics gathering to succeed, got: %v",
			err,
		)
	}

	if len(families) != 3 {
		t.Fatalf(
			"expected 3 metric families, got %d",
			len(families),
		)
	}

	var requestsTotalFound bool
	var requestDurationFound bool

	for _, family := range families {
		switch family.GetName() {
		case "http_requests_total":
			requestsTotalFound = true

			if len(family.GetMetric()) != 1 {
				t.Fatalf(
					"expected 1 request counter metric, got %d",
					len(family.GetMetric()),
				)
			}

			counter := family.GetMetric()[0].GetCounter()

			if counter.GetValue() != 1 {
				t.Fatalf(
					"expected request counter value 1, got %f",
					counter.GetValue(),
				)
			}

		case "http_request_duration_seconds":
			requestDurationFound = true

			if len(family.GetMetric()) != 1 {
				t.Fatalf(
					"expected 1 duration metric, got %d",
					len(family.GetMetric()),
				)
			}

			histogram := family.GetMetric()[0].GetHistogram()

			if histogram.GetSampleCount() != 1 {
				t.Fatalf(
					"expected duration sample count 1, got %d",
					histogram.GetSampleCount(),
				)
			}
		}
	}

	if !requestsTotalFound {
		t.Fatal("http_requests_total metric was not found")
	}

	if !requestDurationFound {
		t.Fatal(
			"http_request_duration_seconds metric was not found",
		)
	}
}
