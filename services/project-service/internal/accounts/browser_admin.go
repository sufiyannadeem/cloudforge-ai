package accounts

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/google/uuid"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type adminInput struct {
	Action    string `json:"action"`
	Username  string `json:"username"`
	Role      string `json:"role"`
	Password  string `json:"password"`
	Email     string `json:"email"`
	ProjectID string `json:"project_id"`
	Level     string `json:"level"`
}

func RegisterAdminRoutes(mux *http.ServeMux, store *Store, key string) {
	mux.HandleFunc("/admin/accounts", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Type", "application/json")
		caller, ok := identity.Verify(r, "project", map[string]string{"frontend": key})
		if !ok || !caller.Human() {
			w.WriteHeader(401)
			return
		}
		if caller.Role != PlatformEngineer {
			w.WriteHeader(403)
			return
		}
		ctx := r.Context()
		if r.Method == http.MethodGet {
			var authorized bool
			if err := store.db.QueryRow(ctx, "SELECT active AND role='platform-engineer' FROM auth_users WHERE username=$1", caller.Subject).Scan(&authorized); err != nil || !authorized {
				w.WriteHeader(403)
				return
			}
			var body json.RawMessage
			err := store.db.QueryRow(ctx, `SELECT jsonb_build_object(
    'users', COALESCE((SELECT jsonb_agg(u) FROM (SELECT username, email, role, active FROM auth_users ORDER BY username LIMIT 200) u),'[]'::jsonb),
    'projects', COALESCE((SELECT jsonb_agg(p) FROM (SELECT id,name,created_by FROM projects ORDER BY name LIMIT 200) p),'[]'::jsonb),
    'memberships', COALESCE((SELECT jsonb_agg(m) FROM (SELECT project_id,username,level FROM project_members ORDER BY project_id,username LIMIT 500) m),'[]'::jsonb),
    'audit', COALESCE((SELECT jsonb_agg(a) FROM (SELECT id,actor,action,username,project_id,level,created_at FROM account_admin_audit ORDER BY id DESC LIMIT 100) a),'[]'::jsonb)
   )`).Scan(&body)
			if err != nil {
				w.WriteHeader(503)
				return
			}
			_, _ = w.Write(body)
			return
		}
		if r.Method != http.MethodPost {
			w.WriteHeader(405)
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 8192))
		digest := sha256.Sum256(body)
		if err != nil || caller.Body != hex.EncodeToString(digest[:]) {
			w.WriteHeader(403)
			return
		}
		var input adminInput
		decoder := json.NewDecoder(strings.NewReader(string(body)))
		decoder.DisallowUnknownFields()
		if decoder.Decode(&input) != nil || decoder.Decode(new(any)) != io.EOF {
			w.WriteHeader(400)
			return
		}
		username := normalizeUsername(input.Username)
		if !usernamePattern.MatchString(username) {
			w.WriteHeader(400)
			return
		}
		tx, err := store.db.Begin(ctx)
		if err != nil {
			w.WriteHeader(503)
			return
		}
		defer tx.Rollback(ctx)
		// Serialize administrative changes, including the last-administrator check.
		if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(2040020)"); err != nil {
			w.WriteHeader(503)
			return
		}
		var activeAdmin bool
		if err = tx.QueryRow(ctx, "SELECT active AND role = 'platform-engineer' FROM auth_users WHERE username=$1", caller.Subject).Scan(&activeAdmin); err != nil || !activeAdmin {
			w.WriteHeader(403)
			return
		}
		var project *uuid.UUID
		if input.Action == "membership" {
			id, err := uuid.Parse(input.ProjectID)
			if err != nil || (input.Level != "maintainer" && input.Level != "viewer" && input.Level != "remove") {
				w.WriteHeader(400)
				return
			}
			project = &id
			var owner *string
			if err := tx.QueryRow(ctx, "SELECT created_by FROM projects WHERE id=$1 FOR UPDATE", id).Scan(&owner); err != nil || (owner != nil && *owner == username) {
				w.WriteHeader(409)
				return
			}
			if input.Level == "remove" {
				_, err = tx.Exec(ctx, "DELETE FROM project_members WHERE project_id=$1 AND username=$2", id, username)
			} else {
				_, err = tx.Exec(ctx, "INSERT INTO project_members(project_id,username,level) VALUES($1,$2,$3) ON CONFLICT(project_id,username) DO UPDATE SET level=excluded.level", id, username, input.Level)
			}
		} else {
			args := []string{input.Action, username}
			switch input.Action {
			case "create", "set-role":
				args = append(args, input.Role)
			case "set-email":
				args = append(args, input.Email)
			case "activate", "deactivate", "revoke":
			default:
				w.WriteHeader(400)
				return
			}
			if input.Action == "deactivate" || input.Action == "set-role" {
				var last bool
				err = tx.QueryRow(ctx, `SELECT active AND role='platform-engineer' AND
      (SELECT count(*) FROM auth_users WHERE active AND role='platform-engineer')=1
      FROM auth_users WHERE username=$1`, username).Scan(&last)
				if err != nil || (last && (input.Action == "deactivate" || input.Role != PlatformEngineer)) {
					w.WriteHeader(409)
					return
				}
			}
			scoped := &Store{db: tx, hashJobs: store.hashJobs}
			err = scoped.Admin(ctx, args, strings.NewReader(input.Password))
			if err == nil && input.Action == "create" && input.Email != "" {
				err = scoped.Admin(ctx, []string{"set-email", username, input.Email}, strings.NewReader(""))
			}
		}
		if err != nil {
			w.WriteHeader(400)
			_ = json.NewEncoder(w).Encode(map[string]string{"error": "Administrative change rejected"})
			return
		}
		auditLevel := input.Level
		if input.Action == "create" || input.Action == "set-role" {
			auditLevel = input.Role
		}
		_, err = tx.Exec(ctx, "INSERT INTO account_admin_audit(nonce,actor,action,username,project_id,level) VALUES($1,$2,$3,$4,$5,$6)", caller.Nonce, caller.Subject, input.Action, username, project, auditLevel)
		if err != nil {
			if pgerr, ok := err.(interface{ SQLState() string }); ok && pgerr.SQLState() == "23505" {
				w.WriteHeader(409)
			} else {
				w.WriteHeader(503)
			}
			return
		}
		if err = tx.Commit(ctx); err != nil {
			w.WriteHeader(503)
			return
		}
		w.WriteHeader(204)
	})
}
