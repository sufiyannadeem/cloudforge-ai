package identity

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestReadinessFailsOnDependencyLossAndShutdownWithoutBypassingAuth(t *testing.T) {
	for _, scenario := range []string{"ready", "database unavailable", "stopping", "application route", "wrong method"} {
		t.Run(scenario, func(t *testing.T) {
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			if scenario == "stopping" {
				cancel()
			}
			calls := 0
			next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { calls++; w.WriteHeader(401) })
			h := WithReadiness(next, func(ctx context.Context) error {
				deadline, ok := ctx.Deadline()
				if !ok || time.Until(deadline) > time.Second {
					t.Fatal("unbounded probe")
				}
				if scenario == "database unavailable" {
					return errors.New("private database details")
				}
				return nil
			}, ctx)
			path, method := "/ready", "GET"
			if scenario == "application route" {
				path = "/api/v1/deployments"
			}
			if scenario == "wrong method" {
				method = "POST"
			}
			response := httptest.NewRecorder()
			h.ServeHTTP(response, httptest.NewRequest(method, path, nil))
			want := 200
			if scenario == "database unavailable" || scenario == "stopping" {
				want = 503
			}
			if scenario == "application route" || scenario == "wrong method" {
				want = 401
			}
			if response.Code != want {
				t.Fatal(response.Code)
			}
			if want == 401 && calls != 1 {
				t.Fatal("authentication bypass")
			}
			if response.Body.String() == "private database details" {
				t.Fatal("dependency details disclosed")
			}
		})
	}
}
