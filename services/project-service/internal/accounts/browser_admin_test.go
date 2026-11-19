package accounts

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

func TestBrowserAdminRejectsUnboundBodyBeforeDatabaseAccess(t *testing.T) {
	mux := http.NewServeMux()
	const key = "browser-admin-body-test-key-32-bytes"
	RegisterAdminRoutes(mux, NewStore(nil), key)
	request := httptest.NewRequest("POST", "/admin/accounts", strings.NewReader(`{"action":"deactivate","username":"admin"}`))
	now := time.Now().Unix()
	request.Header.Set(identity.Header, identity.Sign(identity.Claims{
		Issuer: "frontend", Audience: "project", Subject: "admin", Role: PlatformEngineer,
		Method: "POST", Target: "/admin/accounts", Issued: now, Expiry: now + 25, Nonce: "0123456789abcdef0123456789abcdef",
		Body: strings.Repeat("0", 64),
	}, key))
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	if response.Code != 403 {
		t.Fatalf("unbound body: %d", response.Code)
	}
}
