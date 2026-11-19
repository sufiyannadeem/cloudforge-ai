//go:build integration

package accounts

import (
	"context"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sufiyannadeem/cloudforge-ai-project-service/internal/migration"
)

func TestAccountSessionLifecycle(t *testing.T) {
	url := os.Getenv("DATABASE_URL")
	if url == "" {
		t.Skip("DATABASE_URL is required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		t.Fatal("invalid test database URL")
	}
	admin, err := pgxpool.NewWithConfig(ctx, config.Copy())
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()

	schema := pgx.Identifier{"auth_test_" + uuid.NewString()}.Sanitize()
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+schema); err != nil {
		t.Fatal(err)
	}
	defer func() {
		cleanup, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if _, err := admin.Exec(cleanup, "DROP SCHEMA "+schema+" CASCADE"); err != nil {
			t.Error(err)
		}
	}()
	config.ConnConfig.RuntimeParams["search_path"] = schema
	db, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if err := migration.Run(ctx, db); err != nil {
		t.Fatal(err)
	}
	store := NewStore(db)
	const password = "test-password-for-auth"
	adminAction := func(args ...string) {
		t.Helper()
		if err := store.Admin(ctx, args, strings.NewReader(password+"\n")); err != nil {
			t.Fatal(err)
		}
	}
	adminAction("bootstrap", "engineer")
	t.Run("browser administration", func(t *testing.T) { testBrowserAdministration(t, store) })
	if err := store.Admin(ctx, []string{"bootstrap", "another"}, strings.NewReader(password)); err == nil {
		t.Fatal("bootstrap was reusable")
	}
	adminAction("create", "reliability", SRE)
	adminAction("import-legacy", "legacy", "admin")

	for username, role := range map[string]string{"engineer": PlatformEngineer, "reliability": SRE, "legacy": Developer} {
		identity, token, err := store.Login(ctx, username, password)
		if err != nil || identity.Role != role || token == "" {
			t.Fatalf("login for %s did not issue the expected role: %v", username, err)
		}
		if resolved, err := store.Resolve(ctx, token); err != nil || resolved != identity {
			t.Fatalf("could not resolve %s session: %v", username, err)
		}
	}
	_, profileToken, err := store.Login(ctx, "engineer", password)
	if err != nil {
		t.Fatal(err)
	}
	const email = "engineer@example.test"
	adminAction("set-email", "engineer", email)
	profile, err := store.Resolve(ctx, profileToken)
	if err != nil || profile.Email == nil || *profile.Email != email || profile.Username != "engineer" {
		t.Fatal("updated email missing from the current session", err)
	}
	if _, _, err := store.Login(ctx, email, password); !errors.Is(err, ErrUnauthorized) {
		t.Fatal("email was accepted as a login identifier")
	}
	adminAction("set-email", "engineer", "")
	profile, err = store.Resolve(ctx, profileToken)
	if err != nil || profile.Email != nil {
		t.Fatal("cleared email was still returned", err)
	}
	for _, username := range []string{"engineer", "missing"} {
		if _, _, err := store.Login(ctx, username, "wrong-password"); !errors.Is(err, ErrUnauthorized) {
			t.Fatalf("invalid login accepted: %v", err)
		}
	}
	newSession := func() string {
		t.Helper()
		_, token, err := store.Login(ctx, "reliability", password)
		if err != nil {
			t.Fatal(err)
		}
		return token
	}
	denied := func(token string) {
		t.Helper()
		if _, err := store.Resolve(ctx, token); !errors.Is(err, ErrUnauthorized) {
			t.Fatalf("invalid session accepted: %v", err)
		}
	}

	token := newSession()
	if err := store.Logout(ctx, token); err != nil {
		t.Fatal(err)
	}
	denied(token)
	expired := newSession()
	digest, _ := sessionHash(expired)
	if _, err := db.Exec(ctx, "UPDATE auth_sessions SET expires_at = clock_timestamp() WHERE token_hash = $1", digest[:]); err != nil {
		t.Fatal(err)
	}
	denied(expired)
	denied(strings.Repeat("A", 43))

	token = newSession()
	adminAction("set-role", "reliability", Developer)
	denied(token)
	token = newSession()
	if identity, err := store.Resolve(ctx, token); err != nil || identity.Role != Developer {
		t.Fatalf("role change did not take effect: %v", err)
	}
	adminAction("revoke", "reliability")
	denied(token)
	token = newSession()
	adminAction("deactivate", "reliability")
	denied(token)
	if _, _, err := store.Login(ctx, "reliability", password); !errors.Is(err, ErrUnauthorized) {
		t.Fatalf("deactivated account logged in: %v", err)
	}
	adminAction("activate", "reliability")
	denied(token)
	newSession()
}
