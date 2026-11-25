package handler

import (
	"context"
	"github.com/jackc/pgx/v5"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type workflowScopeDB struct{}
type workflowScopeRow func(...any) error

func (row workflowScopeRow) Scan(dest ...any) error { return row(dest...) }
func (workflowScopeDB) QueryRow(_ context.Context, query string, args ...any) pgx.Row {
	return workflowScopeRow(func(dest ...any) error {
		own := "11111111-1111-4111-8111-111111111111"
		if strings.Contains(query, "FROM projects p") {
			level := ""
			if args[0] == own {
				level = "owner"
			}
			*dest[0].(*string) = level
			return nil
		}
		project := args[0].(string)
		*dest[0].(**string) = &project
		*dest[1].(*string) = identity.ProjectNamespace(project)
		return nil
	})
}

func TestProjectWorkflowDirectAPIDenials(t *testing.T) {
	const own = "11111111-1111-4111-8111-111111111111"
	const foreign = "22222222-2222-4222-8222-222222222222"
	for _, role := range []string{"developer", "sre", "platform-engineer"} {
		for _, action := range []struct{ method, suffix string }{
			{"GET", "logs"}, {"GET", "observability"}, {"GET", "diagnostics"}, {"GET", "rollout"},
			{"POST", "diagnostics"}, {"POST", "run"}, {"POST", "rollback"}, {"POST", "promote"},
		} {
			for _, id := range []string{own, foreign} {
				called := false
				router := NewAuthenticatedRouter(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { called = true; w.WriteHeader(204) }), testFrontendKey, testAIOpsKey, identity.ProjectAccess{DB: workflowScopeDB{}})
				req := httptest.NewRequest(action.method, "/api/v1/deployments/"+id+"/"+action.suffix, nil)
				req.Header.Set("X-CloudForge-Role", "platform-engineer")
				signDeploymentRequest(req, "frontend", testFrontendKey, role)
				result := httptest.NewRecorder()
				router.ServeHTTP(result, req)
				want := 204
				if action.suffix == "promote" && role != "platform-engineer" {
					want = 403
				} else if id == foreign && role != "platform-engineer" && (role == "developer" || (action.method == "POST" && action.suffix != "diagnostics")) {
					want = 404
				}
				if result.Code != want || called != (want == 204) {
					t.Fatalf("%s %s %s as %s: %d, called %v, want %d", action.method, id, action.suffix, role, result.Code, called, want)
				}
			}
		}
	}
}
