package identity

import (
	"context"
	"net/http"
	"time"
)

// WithReadiness exposes only dependency readiness; all application requests retain
// their existing authentication handler. Liveness must not depend on PostgreSQL.
func WithReadiness(next http.Handler, ping func(context.Context) error, stopping context.Context) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/ready" {
			next.ServeHTTP(w, r)
			return
		}
		w.Header().Set("Cache-Control", "no-store")
		ctx, cancel := context.WithTimeout(r.Context(), time.Second)
		defer cancel()
		if stopping.Err() != nil || ping == nil || ping(ctx) != nil {
			http.Error(w, "not ready", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
}
