package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type authorizationDB struct {
	projectID uuid.UUID
	levels    map[string]string
}

type authorizationRow func(...any) error

func (r authorizationRow) Scan(args ...any) error { return r(args...) }

func (d authorizationDB) QueryRow(_ context.Context, _ string, args ...any) pgx.Row {
	return authorizationRow(func(dest ...any) error {
		if args[0] != d.projectID.String() {
			return pgx.ErrNoRows
		}
		*dest[0].(*string) = d.levels[args[1].(string)]
		return nil
	})
}

func (d authorizationDB) Begin(context.Context) (pgx.Tx, error) {
	panic("unexpected membership mutation")
}

func (d authorizationDB) Query(_ context.Context, _ string, args ...any) (pgx.Rows, error) {
	if len(args) != 1 || args[0] != d.projectID {
		panic("observability queried outside the authorized project")
	}
	return &projectCounts{}, nil
}

type projectCounts struct {
	pgx.Rows
	done bool
}

func (*projectCounts) Close()     {}
func (*projectCounts) Err() error { return nil }
func (r *projectCounts) Next() bool {
	if r.done {
		return false
	}
	r.done = true
	return true
}
func (*projectCounts) Scan(dest ...any) error {
	*dest[0].(*string) = "succeeded"
	*dest[1].(*int64) = 2
	return nil
}

func TestProjectAccessScopesObservabilityAndCosts(t *testing.T) {
	id := uuid.New()
	router := ProjectAccess(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}), authorizationDB{id, map[string]string{"alice": "owner", "viewer": "viewer", "maintainer": "maintainer"}})
	path := "/projects/" + id.String()
	for _, tc := range []struct {
		subject, role, method, suffix string
		status                        int
	}{
		{"bob", "developer", "GET", "", 404},
		{"bob", "developer", "GET", "/observability", 404},
		{"bob", "developer", "GET", "/costs", 404},
		{"bob", "developer", "GET", "/logs", 404},
		{"alice", "developer", "GET", "/observability", 200},
		{"viewer", "developer", "GET", "/observability", 200},
		{"alice", "developer", "GET", "/costs", 503},
		{"alice", "developer", "GET", "/logs", 503},
		{"viewer", "developer", "PATCH", "", 403},
		{"maintainer", "developer", "PATCH", "", 204},
		{"maintainer", "developer", "DELETE", "", 403},
		{"alice", "developer", "DELETE", "", 204},
		{"operator", "platform-engineer", "GET", "", 204},
		{"observer", "sre", "GET", "", 404},
	} {
		req := identity.WithClaims(httptest.NewRequest(tc.method, path+tc.suffix, nil),
			identity.Claims{Issuer: "frontend", Subject: tc.subject, Role: tc.role})
		req.Header.Set("X-CloudForge-Role", "platform-engineer")
		resp := httptest.NewRecorder()
		router.ServeHTTP(resp, req)
		if resp.Code != tc.status {
			t.Errorf("%s %s as %s returned %d, want %d", tc.method, tc.suffix, tc.subject, resp.Code, tc.status)
		}
		if tc.status == 200 {
			var result struct {
				ProjectID uuid.UUID        `json:"project_id"`
				Counts    map[string]int64 `json:"deployments_by_status"`
			}
			if err := json.Unmarshal(resp.Body.Bytes(), &result); err != nil || result.ProjectID != id || result.Counts["succeeded"] != 2 {
				t.Fatal("project monitoring returned unexpected data")
			}
		}
	}
}
