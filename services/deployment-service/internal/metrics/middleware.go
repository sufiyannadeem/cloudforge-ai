package metrics

import (
	"net/http"
	"time"
)

type responseWriter struct {
	http.ResponseWriter
	statusCode  int
	wroteHeader bool
}

func newResponseWriter(
	writer http.ResponseWriter,
) *responseWriter {
	return &responseWriter{
		ResponseWriter: writer,
		statusCode:     http.StatusOK,
	}
}

func (w *responseWriter) WriteHeader(
	statusCode int,
) {
	if w.wroteHeader {
		return
	}

	w.statusCode = statusCode
	w.wroteHeader = true

	w.ResponseWriter.WriteHeader(statusCode)
}

func (w *responseWriter) Write(
	body []byte,
) (int, error) {
	if !w.wroteHeader {
		w.WriteHeader(http.StatusOK)
	}

	return w.ResponseWriter.Write(body)
}

func Middleware(
	metrics *Metrics,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(
			func(
				w http.ResponseWriter,
				r *http.Request,
			) {
				start := time.Now()

				metrics.RequestsInFlight.Inc()

				defer metrics.RequestsInFlight.Dec()

				recorder := newResponseWriter(w)

				next.ServeHTTP(recorder, r)

				route := r.Pattern

				if route == "" {
					route = "unknown"
				}

				metrics.ObserveRequest(
					r.Method,
					route,
					recorder.statusCode,
					time.Since(start),
				)
			},
		)
	}
}
