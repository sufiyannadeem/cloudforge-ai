package accounts

import (
	"bytes"
	"context"
	"encoding/base64"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestLegacyRolesNeverImportAsAdministrator(t *testing.T) {
	for input, want := range map[string]string{
		"viewer": Developer, "devops": Developer, "admin": Developer,
		PlatformEngineer: Developer, SRE: SRE, "unknown": "",
	} {
		if got := legacyRole(input); got != want {
			t.Errorf("legacy role %q mapped to %q, want %q", input, got, want)
		}
	}
	for _, role := range []string{Developer, SRE, PlatformEngineer} {
		if !validRole(role) {
			t.Errorf("canonical role %q rejected", role)
		}
	}
	if validRole("admin") || validRole("devops") || validRole("viewer") {
		t.Fatal("a legacy role was accepted as canonical")
	}
}

func TestPasswordAndSessionHashes(t *testing.T) {
	salt := make([]byte, 32)
	first, err := hashPassword("test-account-password", salt)
	if err != nil {
		t.Fatal(err)
	}
	second, err := hashPassword("wrong-password", salt)
	if err != nil || bytes.Equal(first, second) {
		t.Fatal("a different password produced the same hash")
	}
	salt[0] = 1
	third, err := hashPassword("test-account-password", salt)
	if err != nil || bytes.Equal(first, third) {
		t.Fatal("a different salt produced the same hash")
	}

	raw := make([]byte, 32)
	token := base64.RawURLEncoding.EncodeToString(raw)
	digest, ok := sessionHash(token)
	if !ok || bytes.Equal(raw, digest[:]) {
		t.Fatal("session must be stored by digest")
	}
	for _, forged := range []string{token + ".", token[:42] + "B", "legacy.signed.session"} {
		if _, ok := sessionHash(forged); ok {
			t.Fatal("noncanonical or legacy session accepted")
		}
	}
}

type testSessions struct{}

func (testSessions) Login(_ context.Context, username, password string) (Identity, string, error) {
	if username != "engineer" || password != "test-account-password" {
		return Identity{}, "", ErrUnauthorized
	}
	return Identity{Username: username, Role: PlatformEngineer, ExpiresAt: 2_000_000_000}, "test-token", nil
}

func (testSessions) Resolve(_ context.Context, token string) (Identity, error) {
	if token != "test-token" {
		return Identity{}, ErrUnauthorized
	}
	return Identity{Username: "engineer", Role: PlatformEngineer}, nil
}

func (testSessions) Logout(_ context.Context, token string) error {
	if token != "test-token" {
		return ErrUnauthorized
	}
	return nil
}

func TestInternalAccountRoutes(t *testing.T) {
	const key = "test-internal-token-at-least-32-bytes"
	mux := http.NewServeMux()
	RegisterRoutes(mux, testSessions{}, key)
	for _, tc := range []struct {
		name, operation, body, internalToken, bearer string
		status                                       int
	}{
		{"login", "login", `{"username":"engineer","password":"test-account-password"}`, key, "", 200},
		{"wrong credentials", "login", `{"username":"engineer","password":"wrong"}`, key, "", 401},
		{"direct backend", "login", `{}`, "", "", 401},
		{"forged session", "session", "", key, "Bearer attacker-token", 401},
		{"missing bearer scheme", "session", "", key, "test-token", 401},
		{"resolved session", "session", "", key, "Bearer test-token", 200},
		{"logout", "logout", "", key, "Bearer test-token", 204},
	} {
		t.Run(tc.name, func(t *testing.T) {
			request := httptest.NewRequest("POST", "/internal/auth/"+tc.operation, strings.NewReader(tc.body))
			if tc.internalToken != "" {
				now := time.Now().Unix()
				request.Header.Set(identity.Header, identity.Sign(identity.Claims{
					Issuer: "frontend", Audience: "project", Method: request.Method, Target: request.URL.RequestURI(),
					Issued: now, Expiry: now + 25, Nonce: "00112233445566778899aabbccddeeff",
				}, tc.internalToken))
			}
			request.Header.Set("X-CloudForge-Role", PlatformEngineer)
			request.Header.Set("Authorization", tc.bearer)
			recorder := httptest.NewRecorder()
			mux.ServeHTTP(recorder, request)
			if recorder.Code != tc.status || recorder.Header().Get("Cache-Control") != "no-store" {
				t.Fatalf("got HTTP %d, want %d with no-store", recorder.Code, tc.status)
			}
		})
	}
}

func TestOptionalAccountEmail(t *testing.T) {
	for _, input := range []string{"", "a+b@example.test", "a.b@sub.example.test"} {
		value, err := optionalEmail(input)
		if err != nil || (input == "" && value != nil) || (input != "" && (value == nil || *value != input)) {
			t.Errorf("unexpected validation result for %q", input)
		}
	}
	for _, input := range []string{"name <a@example.test>", "a@example", "a..b@example.test", "a@-example.test", "a@b.test\n", strings.Repeat("a", 65) + "@example.test"} {
		if _, err := optionalEmail(input); err == nil {
			t.Errorf("accepted invalid address %q", input)
		}
	}
}
