package metrics

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/prometheus/client_golang/prometheus"
)

func TestMiddlewareRecordsSuccessfulRequest(t *testing.T) {
	t.Parallel()

	serviceMetrics := New()
	registry := prometheus.NewRegistry()

	if err := serviceMetrics.Register(registry); err != nil {
		t.Fatalf(
			"expected metrics registration to succeed, got: %v",
			err,
		)
	}

	handler := http.HandlerFunc(
		func(
			w http.ResponseWriter,
			r *http.Request,
		) {
			w.WriteHeader(http.StatusCreated)

			_, _ = w.Write([]byte(`{"status":"created"}`))
		},
	)

	instrumentedHandler := Middleware(serviceMetrics)(handler)

	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/deployments",
		nil,
	)

	recorder := httptest.NewRecorder()

	instrumentedHandler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusCreated {
		t.Fatalf(
			"expected status 201, got %d",
			recorder.Code,
		)
	}

	families, err := registry.Gather()
	if err != nil {
		t.Fatalf(
			"expected metrics gathering to succeed, got: %v",
			err,
		)
	}

	var requestCounterValue float64

	for _, family := range families {
		if family.GetName() != "http_requests_total" {
			continue
		}

		for _, metric := range family.GetMetric() {
			matchedMethod := false
			matchedStatus := false

			for _, label := range metric.GetLabel() {
				switch label.GetName() {
				case "method":
					matchedMethod = label.GetValue() == "POST"
				case "status":
					matchedStatus = label.GetValue() == "201"
				}
			}

			if matchedMethod && matchedStatus {
				requestCounterValue = metric.GetCounter().GetValue()
			}
		}
	}

	if requestCounterValue != 1 {
		t.Fatalf(
			"expected matching request counter value 1, got %f",
			requestCounterValue,
		)
	}
}

func TestMiddlewareTracksInFlightRequests(t *testing.T) {
	t.Parallel()

	serviceMetrics := New()

	handler := http.HandlerFunc(
		func(
			w http.ResponseWriter,
			r *http.Request,
		) {
			if serviceMetrics.RequestsInFlight == nil {
				t.Fatal("in-flight gauge must not be nil")
			}

			_, _ = w.Write([]byte("ok"))
		},
	)

	instrumentedHandler := Middleware(serviceMetrics)(handler)

	request := httptest.NewRequest(
		http.MethodGet,
		"/health",
		nil,
	)

	recorder := httptest.NewRecorder()

	instrumentedHandler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"expected status 200, got %d",
			recorder.Code,
		)
	}
}

func TestResponseWriterDefaultsToStatusOK(t *testing.T) {
	t.Parallel()

	recorder := httptest.NewRecorder()
	writer := newResponseWriter(recorder)

	_, err := writer.Write([]byte("ok"))
	if err != nil {
		t.Fatalf(
			"expected write to succeed, got: %v",
			err,
		)
	}

	if writer.statusCode != http.StatusOK {
		t.Fatalf(
			"expected status 200, got %d",
			writer.statusCode,
		)
	}

	if !writer.wroteHeader {
		t.Fatal("expected response writer to mark header as written")
	}
}
