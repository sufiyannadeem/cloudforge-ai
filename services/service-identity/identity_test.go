package identity

import (
	"net/http/httptest"
	"testing"
	"time"
)

func TestVerifyRequestBinding(t *testing.T) {
	const key = "project-specific-test-key-0123456789"
	now := time.Now().Unix()
	base := Claims{Issuer: "frontend", Audience: "project", Subject: "operator", Role: "developer",
		Method: "GET", Target: "/projects?limit=1", Issued: now, Expiry: now + 25, Nonce: "11223344556677889900aabbccddeeff"}
	for name, alter := range map[string]func(*Claims){
		"valid":     func(*Claims) {},
		"issuer":    func(c *Claims) { c.Issuer = "aiops" },
		"audience":  func(c *Claims) { c.Audience = "deployment" },
		"expired":   func(c *Claims) { c.Expiry = now - 1 },
		"lifetime":  func(c *Claims) { c.Expiry = now + 90 },
		"method":    func(c *Claims) { c.Method = "POST" },
		"target":    func(c *Claims) { c.Target = "/projects?limit=2" },
		"signature": func(*Claims) {},
	} {
		t.Run(name, func(t *testing.T) {
			claims := base
			alter(&claims)
			signingKey := key
			if name == "signature" {
				signingKey += "-wrong"
			}
			req := httptest.NewRequest("GET", "/projects?limit=1", nil)
			req.Header.Set(Header, Sign(claims, signingKey))
			req.Header.Set("X-CloudForge-Role", "platform-engineer")
			actual, ok := Verify(req, "project", map[string]string{"frontend": key})
			if ok != (name == "valid") || (ok && (!actual.Human() || actual.Role != "developer")) {
				t.Fatal("unexpected identity verification result")
			}
		})
	}
}
