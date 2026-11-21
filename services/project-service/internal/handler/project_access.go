package handler

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type projectAccessDB interface {
	identity.ProjectDB
	Begin(context.Context) (pgx.Tx, error)
	Query(context.Context, string, ...any) (pgx.Rows, error)
}

// ProjectAccess wraps project endpoints after the signed human identity check.
func ProjectAccess(next http.Handler, db projectAccessDB) http.Handler {
	access := identity.ProjectAccess{DB: db}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		caller := identity.FromContext(r.Context())
		if !caller.Human() {
			writeError(w, http.StatusUnauthorized, "verified account required")
			return
		}
		admin := caller.Role == "platform-engineer"
		if r.URL.Path == "/projects" {
			if r.Method == http.MethodPost && !admin && caller.Role != "developer" {
				writeError(w, http.StatusForbidden, "project operation denied")
				return
			}
			next.ServeHTTP(w, r)
			return
		}

		parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/projects/"), "/")
		projectID, err := uuid.Parse(parts[0])
		if err != nil || projectID == uuid.Nil {
			writeError(w, http.StatusNotFound, "project not found")
			return
		}
		level, err := access.Level(r.Context(), projectID.String(), caller.Subject)
		if err == nil && !admin {
			err = identity.CheckMembership(level, false)
		}
		if err != nil {
			writeError(w, identity.AccessStatus(err), "project access denied")
			return
		}
		if len(parts) > 1 {
			switch {
			case len(parts) == 2 && parts[1] == "observability" && r.Method == http.MethodGet:
				projectObservability(w, r, db, projectID)
			case len(parts) == 2 && parts[1] == "costs" && r.Method == http.MethodGet:
				writeError(w, http.StatusServiceUnavailable, "verified project cost attribution unavailable")
			case len(parts) == 2 && parts[1] == "logs" && r.Method == http.MethodGet:
				writeError(w, http.StatusServiceUnavailable, "verified project logs unavailable")
			case (parts[1] == "members" && len(parts) <= 3) || (parts[1] == "owner" && len(parts) == 2):
				projectMembership(w, r, db, projectID, parts)
			default:
				writeError(w, http.StatusNotFound, "project route not found")
			}
			return
		}

		if !admin && r.Method != http.MethodGet && r.Method != http.MethodHead {
			allowed := caller.Role == "developer" &&
				((r.Method == http.MethodPatch && (level == "owner" || level == "maintainer")) ||
					(r.Method == http.MethodDelete && level == "owner"))
			if !allowed {
				writeError(w, http.StatusForbidden, "project operation denied")
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func projectMembership(w http.ResponseWriter, r *http.Request, db projectAccessDB, projectID uuid.UUID, parts []string) {
	ctx := r.Context()
	caller := identity.FromContext(ctx)
	admin := caller.Role == "platform-engineer"
	tx, err := db.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "membership unavailable")
		return
	}
	defer tx.Rollback(ctx)

	var owner *string
	err = tx.QueryRow(ctx, "SELECT created_by FROM projects WHERE id = $1 FOR UPDATE", projectID).Scan(&owner)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "project not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "membership unavailable")
		return
	}
	if !admin && (owner == nil || *owner != caller.Subject || parts[1] == "owner") {
		writeError(w, http.StatusForbidden, "project administration denied")
		return
	}

	switch {
	case parts[1] == "owner" && r.Method == http.MethodPut:
		var input struct {
			Username string `json:"username"`
		}
		if err := decodeJSONBody(w, r, &input); err != nil {
			return
		}
		tag, updateErr := tx.Exec(ctx, `
			UPDATE projects SET created_by = $2
			WHERE id = $1 AND EXISTS (SELECT 1 FROM auth_users WHERE username = $2 AND active)
		`, projectID, input.Username)
		err = updateErr
		if err == nil && tag.RowsAffected() == 0 {
			writeError(w, http.StatusNotFound, "account not found")
			return
		}
		if err == nil {
			_, err = tx.Exec(ctx, "DELETE FROM project_members WHERE project_id = $1 AND username = $2", projectID, input.Username)
		}
	case parts[1] == "members" && len(parts) == 2 && r.Method == http.MethodGet:
		projectMembers(w, r, tx, projectID, owner)
		return
	case parts[1] == "members" && len(parts) == 3 && r.Method == http.MethodPut:
		if owner == nil {
			writeError(w, http.StatusConflict, "assign a verified owner before granting membership")
			return
		}
		username := parts[2]
		var input struct {
			Level string `json:"level"`
		}
		if err := decodeJSONBody(w, r, &input); err != nil {
			return
		}
		if input.Level != "viewer" && input.Level != "maintainer" {
			writeError(w, http.StatusBadRequest, "membership level must be viewer or maintainer")
			return
		}
		if owner != nil && *owner == username {
			writeError(w, http.StatusConflict, "project owner has implicit membership")
			return
		}
		tag, insertErr := tx.Exec(ctx, `
			INSERT INTO project_members (project_id, username, level)
			SELECT $1::uuid, username, $3 FROM auth_users WHERE username = $2 AND active
			ON CONFLICT (project_id, username) DO UPDATE SET level = EXCLUDED.level
		`, projectID, username, input.Level)
		err = insertErr
		if err == nil && tag.RowsAffected() == 0 {
			writeError(w, http.StatusNotFound, "account not found")
			return
		}
	case parts[1] == "members" && len(parts) == 3 && r.Method == http.MethodDelete:
		_, err = tx.Exec(ctx, "DELETE FROM project_members WHERE project_id = $1 AND username = $2", projectID, parts[2])
	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	if err == nil {
		err = tx.Commit(ctx)
	}
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "membership unavailable")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func projectMembers(w http.ResponseWriter, r *http.Request, tx pgx.Tx, projectID uuid.UUID, owner *string) {
	rows, err := tx.Query(r.Context(), `SELECT username, level FROM project_members WHERE project_id = $1 ORDER BY username`, projectID)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "membership unavailable")
		return
	}
	defer rows.Close()
	members := make([]map[string]string, 0)
	if owner != nil {
		members = append(members, map[string]string{"username": *owner, "level": "owner"})
	}
	for rows.Next() {
		var username, level string
		if err := rows.Scan(&username, &level); err != nil {
			writeError(w, http.StatusServiceUnavailable, "membership unavailable")
			return
		}
		members = append(members, map[string]string{"username": username, "level": level})
	}
	if rows.Err() != nil {
		writeError(w, http.StatusServiceUnavailable, "membership unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"members": members})
}

func projectObservability(w http.ResponseWriter, r *http.Request, db projectAccessDB, projectID uuid.UUID) {
	rows, err := db.Query(r.Context(), `SELECT status, count(*) FROM deployments WHERE project_id = $1 GROUP BY status`, projectID)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "project deployment data unavailable")
		return
	}
	defer rows.Close()
	counts := map[string]int64{}
	for rows.Next() {
		var status string
		var count int64
		if err := rows.Scan(&status, &count); err != nil {
			writeError(w, http.StatusServiceUnavailable, "project deployment data unavailable")
			return
		}
		counts[status] = count
	}
	if rows.Err() != nil {
		writeError(w, http.StatusServiceUnavailable, "project deployment data unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"project_id": projectID, "deployments_by_status": counts})
}
