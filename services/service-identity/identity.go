package identity

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strings"
	"time"
)

const Header = "X-CloudForge-Identity"

type Claims struct {
	Issuer   string `json:"iss"`
	Audience string `json:"aud"`
	Subject  string `json:"sub,omitempty"`
	Role     string `json:"role,omitempty"`
	Method   string `json:"method"`
	Target   string `json:"target"`
	Issued   int64  `json:"iat"`
	Expiry   int64  `json:"exp"`
	Nonce    string `json:"nonce"`
	Body     string `json:"body,omitempty"`
}

func ValidKey(key string) bool {
	return len(key) >= 32 && !strings.Contains(strings.ToLower(key), "replace-with")
}

func ValidRole(role string) bool {
	return role == "platform-engineer" || role == "sre" || role == "developer"
}

func Verify(r *http.Request, audience string, callerKeys map[string]string) (Claims, bool) {
	values := r.Header.Values(Header)
	if len(values) != 1 || len(values[0]) > 8192 {
		return Claims{}, false
	}
	payload, signature, ok := strings.Cut(values[0], ".")
	if !ok {
		return Claims{}, false
	}
	data, err := base64.RawURLEncoding.Strict().DecodeString(payload)
	var claims Claims
	if err != nil || json.Unmarshal(data, &claims) != nil {
		return Claims{}, false
	}
	key := callerKeys[claims.Issuer]
	sig, err := hex.DecodeString(signature)
	if !ValidKey(key) || err != nil {
		return Claims{}, false
	}
	mac := hmac.New(sha256.New, []byte(key))
	mac.Write([]byte(payload))
	if !hmac.Equal(sig, mac.Sum(nil)) {
		return Claims{}, false
	}

	now := time.Now().Unix()
	nonce, nonceErr := hex.DecodeString(claims.Nonce)
	if claims.Audience != audience || claims.Method != r.Method || claims.Target != r.URL.RequestURI() ||
		claims.Issued < now-30 || claims.Issued > now+5 || claims.Expiry <= now ||
		claims.Expiry <= claims.Issued || claims.Expiry-claims.Issued > 30 ||
		nonceErr != nil || len(nonce) != 16 {
		return Claims{}, false
	}
	return claims, true
}

var username = regexp.MustCompile(`^[a-z0-9][a-z0-9._@-]{0,127}$`)

func (c Claims) Human() bool {
	return c.Issuer == "frontend" && username.MatchString(c.Subject) && ValidRole(c.Role)
}

func (c Claims) Service() bool {
	return c.Subject == "" && c.Role == ""
}

type contextKey struct{}

func WithClaims(r *http.Request, claims Claims) *http.Request {
	return r.WithContext(context.WithValue(r.Context(), contextKey{}, claims))
}

func FromContext(ctx context.Context) Claims {
	claims, _ := ctx.Value(contextKey{}).(Claims)
	return claims
}

var ErrReplay = errors.New("identity assertion already used")

// Sign encodes the signed wire format for trusted callers.
func Sign(claims Claims, key string) string {
	data, _ := json.Marshal(claims)
	payload := base64.RawURLEncoding.EncodeToString(data)
	mac := hmac.New(sha256.New, []byte(key))
	mac.Write([]byte(payload))
	return payload + "." + hex.EncodeToString(mac.Sum(nil))
}
