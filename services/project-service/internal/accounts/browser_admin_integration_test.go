//go:build integration

package accounts

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func testBrowserAdministration(t *testing.T, store *Store) {
	const key = "browser-admin-test-key-at-least-32-bytes"
	mux := http.NewServeMux()
	RegisterAdminRoutes(mux, store, key)
	request := func(method, body, role, nonce string, signed bool) *httptest.ResponseRecorder {
		t.Helper()
		req := httptest.NewRequest(method, "/admin/accounts", strings.NewReader(body))
		digest := sha256.Sum256([]byte(body))
		now := time.Now().Unix()
		subject := "engineer"
		if role == "forged-admin" {
			subject = "browser-user"
			role = PlatformEngineer
		}
		if signed {
			req.Header.Set(identity.Header, identity.Sign(identity.Claims{
				Issuer: "frontend", Audience: "project", Subject: subject, Role: role, Method: method, Target: "/admin/accounts",
				Issued: now, Expiry: now + 25, Nonce: nonce, Body: hex.EncodeToString(digest[:]),
			}, key))
		}
		req.Header.Set("X-CloudForge-Role", PlatformEngineer)
		result := httptest.NewRecorder()
		mux.ServeHTTP(result, req)
		return result
	}
	create := `{"action":"create","username":"browser-user","role":"developer","password":"browser-test-password","email":"user@example.test"}`
	for _, role := range []string{Developer, SRE} {
		if res := request("POST", create, role, strings.ReplaceAll(uuid.NewString(), "-", ""), true); res.Code != 403 {
			t.Fatalf("role %s: %d", role, res.Code)
		}
	}
	if res := request("GET", "", PlatformEngineer, strings.ReplaceAll(uuid.NewString(), "-", ""), false); res.Code != 401 {
		t.Fatalf("unsigned: %d", res.Code)
	}
	nonce := strings.ReplaceAll(uuid.NewString(), "-", "")
	if res := request("POST", create, PlatformEngineer, nonce, true); res.Code != 204 {
		t.Fatalf("create: %d %s", res.Code, res.Body)
	}
	if res := request("POST", create, PlatformEngineer, nonce, true); res.Code != 400 && res.Code != 409 {
		t.Fatalf("replay: %d", res.Code)
	}
	if res := request("GET", "", "forged-admin", strings.ReplaceAll(uuid.NewString(), "-", ""), true); res.Code != 403 {
		t.Fatalf("forged administrator role: %d", res.Code)
	}
	_, token, err := store.Login(t.Context(), "browser-user", "browser-test-password")
	if err != nil {
		t.Fatal(err)
	}
	revoke := `{"action":"revoke","username":"browser-user"}`
	nonce = strings.ReplaceAll(uuid.NewString(), "-", "")
	if res := request("POST", revoke, PlatformEngineer, nonce, true); res.Code != 204 {
		t.Fatalf("revoke: %d", res.Code)
	}
	if _, err = store.Resolve(t.Context(), token); err == nil {
		t.Fatal("revoked session accepted")
	}
	if res := request("POST", revoke, PlatformEngineer, nonce, true); res.Code != 409 {
		t.Fatalf("replayed mutation: %d", res.Code)
	}
	if res := request("POST", `{"action":"deactivate","username":"engineer"}`, PlatformEngineer, strings.ReplaceAll(uuid.NewString(), "-", ""), true); res.Code != 409 {
		t.Fatalf("last admin: %d", res.Code)
	}
	project := uuid.New()
	if _, err = store.db.Exec(t.Context(), "INSERT INTO projects(id,name,repository_url,default_branch,created_by) VALUES($1,'admin-test','https://example.test/repo','main','engineer')", project); err != nil {
		t.Fatal(err)
	}
	member := `{"action":"membership","username":"browser-user","project_id":"` + project.String() + `","level":"viewer"}`
	if res := request("POST", member, PlatformEngineer, strings.ReplaceAll(uuid.NewString(), "-", ""), true); res.Code != 204 {
		t.Fatalf("membership: %d", res.Code)
	}
	res := request("GET", "", PlatformEngineer, strings.ReplaceAll(uuid.NewString(), "-", ""), true)
	var body struct {
		Audit []struct{ Action string }
		Users []struct{ Username string }
	}
	if err = json.Unmarshal(res.Body.Bytes(), &body); err != nil || res.Code != 200 || len(body.Audit) != 3 {
		t.Fatalf("audit: %d %s", res.Code, res.Body)
	}
	if strings.Contains(res.Body.String(), "password_hash") || strings.Contains(res.Body.String(), "browser-test-password") {
		t.Fatal("secret in response")
	}
}
