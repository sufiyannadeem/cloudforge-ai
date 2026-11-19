package identity

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"github.com/jackc/pgx/v5"
)

const MembershipPredicate = `(p.created_by IS NOT NULL AND (p.created_by = $3 OR EXISTS (
	SELECT 1 FROM project_members pm WHERE pm.project_id = p.id AND pm.username = $3
)))`

var (
	ErrProjectHidden      = errors.New("resource not found")
	ErrProjectWrite       = errors.New("insufficient project membership")
	ErrProjectUnavailable = errors.New("project authorization unavailable")
)

type ProjectDB interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

type ProjectAccess struct{ DB ProjectDB }

func ListMember(ctx context.Context) string {
	if caller := FromContext(ctx); caller.Role == "developer" {
		return caller.Subject
	}
	return ""
}

func CheckMembership(level string, write bool) error {
	switch level {
	case "owner", "maintainer":
		return nil
	case "viewer":
		if write {
			return ErrProjectWrite
		}
		return nil
	default:
		return ErrProjectHidden
	}
}

func AccessStatus(err error) int {
	switch {
	case errors.Is(err, ErrProjectHidden):
		return http.StatusNotFound
	case errors.Is(err, ErrProjectWrite):
		return http.StatusForbidden
	default:
		return http.StatusServiceUnavailable
	}
}

func (a ProjectAccess) Level(ctx context.Context, projectID, subject string) (string, error) {
	if a.DB == nil {
		return "", ErrProjectUnavailable
	}
	var level string
	err := a.DB.QueryRow(ctx, `
		SELECT CASE WHEN p.created_by IS NULL THEN '' WHEN p.created_by = $2 THEN 'owner' ELSE COALESCE(pm.level, '') END
		FROM projects p
		LEFT JOIN project_members pm ON pm.project_id = p.id AND pm.username = $2
		WHERE p.id = $1::text::uuid
	`, projectID, subject).Scan(&level)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrProjectHidden
	}
	if err != nil {
		return "", ErrProjectUnavailable
	}
	return level, nil
}

func (a ProjectAccess) Resource(ctx context.Context, service, id string, write bool) error {
	caller := FromContext(ctx)
	if caller.Role == "platform-engineer" || (caller.Role == "sre" && !write) {
		return nil
	}
	if a.DB == nil || !caller.Human() {
		return errors.New("project authorization unavailable")
	}
	var query string
	switch service {
	case "infrastructure":
		query = `SELECT r.project_id::text, '' FROM infrastructure_resources r WHERE r.id = $1::text::uuid`
	case "deployment":
		query = `SELECT r.project_id::text, r.namespace FROM deployments r WHERE r.id = $1::text::uuid`
	default:
		return errors.New("unknown project resource")
	}
	var projectID *string
	var namespace string
	err := a.DB.QueryRow(ctx, query, id).Scan(&projectID, &namespace)
	if errors.Is(err, pgx.ErrNoRows) || (err == nil && projectID == nil) {
		return ErrProjectHidden
	}
	if err != nil {
		return err
	}
	level, err := a.Level(ctx, *projectID, caller.Subject)
	if err != nil {
		return err
	}
	if err := CheckMembership(level, write); err != nil {
		return err
	}
	if write && service == "deployment" && namespace != ProjectNamespace(*projectID) {
		return ErrProjectWrite
	}
	return nil
}

func ProjectNamespace(id string) string { return "cf-" + strings.ToLower(id) }

type projectAccessKey struct{}

func (a ProjectAccess) Attach(r *http.Request) *http.Request {
	return r.WithContext(context.WithValue(r.Context(), projectAccessKey{}, a))
}

func RequireProjectWrite(ctx context.Context, projectID string) error {
	caller := FromContext(ctx)
	if caller.Issuer == "" || caller.Role == "platform-engineer" {
		return nil
	}
	access, _ := ctx.Value(projectAccessKey{}).(ProjectAccess)
	level, err := access.Level(ctx, projectID, caller.Subject)
	if err != nil {
		return err
	}
	return CheckMembership(level, true)
}
