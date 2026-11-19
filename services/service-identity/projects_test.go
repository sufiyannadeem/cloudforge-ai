package identity

import (
	"context"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5"
)

type scopeDB struct {
	members map[string]string
}

type scopeRow func(...any) error

func (r scopeRow) Scan(values ...any) error { return r(values...) }

func (db scopeDB) QueryRow(_ context.Context, query string, args ...any) pgx.Row {
	return scopeRow(func(values ...any) error {
		id := args[0].(string)
		if strings.Contains(query, "FROM projects p") {
			if id == "missing" {
				return pgx.ErrNoRows
			}
			*values[0].(*string) = db.members[id+"/"+args[1].(string)]
			return nil
		}
		if id == "missing" {
			return pgx.ErrNoRows
		}
		project := id
		if id != "orphan" {
			*values[0].(**string) = &project
		}
		namespace := ProjectNamespace(project)
		if id == "unsafe" {
			namespace = "shared"
		}
		*values[1].(*string) = namespace
		return nil
	})
}

func TestProjectResourceIsolation(t *testing.T) {
	db := scopeDB{map[string]string{
		"project-a/alice": "owner", "project-b/bob": "owner",
		"project-b/alice": "viewer", "unsafe/alice": "owner",
	}}
	access := ProjectAccess{DB: db}
	ctx := func(actor, role string) context.Context {
		return access.Attach(WithClaims(httptest.NewRequest("GET", "/", nil),
			Claims{Issuer: "frontend", Subject: actor, Role: role})).Context()
	}
	assert := func(got, want error) {
		t.Helper()
		if !errors.Is(got, want) {
			t.Fatalf("project access = %v, want %v", got, want)
		}
	}
	alice := ctx("alice", "developer")
	for _, service := range []string{"infrastructure", "deployment"} {
		assert(access.Resource(alice, service, "project-a", true), nil)
		assert(access.Resource(alice, service, "project-b", false), nil)
		assert(access.Resource(alice, service, "project-b", true), ErrProjectWrite)
		assert(access.Resource(ctx("bob", "developer"), service, "project-a", false), ErrProjectHidden)
		assert(access.Resource(alice, service, "missing", false), ErrProjectHidden)
		assert(access.Resource(alice, service, "legacy", false), ErrProjectHidden)
		assert(access.Resource(alice, service, "orphan", false), ErrProjectHidden)
		assert(access.Resource(ctx("sre", "sre"), service, "legacy", false), nil)
		assert(access.Resource(ctx("operator", "platform-engineer"), service, "legacy", true), nil)
	}
	assert(RequireProjectWrite(ctx("bob", "developer"), "project-a"), ErrProjectHidden)
	assert(access.Resource(alice, "deployment", "unsafe", true), ErrProjectWrite)
	db.members["project-b/alice"] = "maintainer"
	assert(RequireProjectWrite(alice, "project-b"), nil)
	delete(db.members, "project-b/alice")
	assert(RequireProjectWrite(alice, "project-b"), ErrProjectHidden)
	assert(access.Resource(alice, "deployment", "project-b", false), ErrProjectHidden)
}
