package metrics

import (
	"crypto/subtle"
	"net/http"
	"os"
	"strings"
)

// New project-labelled telemetry is monitoring-only, never exposed by a human
// frontend assertion. The isolated inference workload has no scrape credential.
func ProtectEvidenceMetrics(next http.Handler, path string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key, err := os.ReadFile(path)
		token := strings.TrimSpace(string(key))
		if err != nil || len(token) < 32 || len(token) > 4096 || strings.Contains(strings.ToLower(token), "replace-with") {
			http.Error(w, "Evidence scrape identity unavailable", 503)
			return
		}
		for _, name := range []string{"CLOUDFORGE_FRONTEND_KEY", "CLOUDFORGE_AIOPS_DEPLOYMENT_KEY", "CLOUDFORGE_INTERNAL_TOKEN"} {
			if token == os.Getenv(name) {
				http.Error(w, "Dedicated monitoring identity required", 503)
				return
			}
		}
		if len(r.Header.Values("Authorization")) != 1 || subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+token)) != 1 {
			http.Error(w, "Monitoring identity required", 401)
			return
		}
		w.Header().Set("Cache-Control", "private, no-store")
		next.ServeHTTP(w, r)
	})
}
