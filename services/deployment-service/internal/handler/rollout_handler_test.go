package handler

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/executor"
	"github.com/sufiyannadeem/cloudforge-ai-deployment-service/internal/repository"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type promotionFixture struct {
	mu              sync.Mutex
	state           executor.RolloutState
	claims, patches int
	outcomes        []bool
	patchErr        error
}

func (f *promotionFixture) RolloutState(context.Context, uuid.UUID) (executor.RolloutState, error) {
	return f.state, nil
}
func (f *promotionFixture) Promote(context.Context, uuid.UUID, executor.RolloutState) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.patches++
	return f.patchErr
}
func (f *promotionFixture) ClaimPromotion(context.Context, uuid.UUID, string, string) (uuid.UUID, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.claims++
	if f.claims > 1 {
		return uuid.Nil, repository.ErrPromotionDenied
	}
	return uuid.New(), nil
}
func (f *promotionFixture) CompletePromotion(_ context.Context, _ uuid.UUID, submitted bool) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.outcomes = append(f.outcomes, submitted)
	return nil
}
func (f *promotionFixture) PromotionHistory(context.Context, uuid.UUID) ([]repository.PromotionAudit, error) {
	return []repository.PromotionAudit{}, nil
}
func readyPromotionFixture() *promotionFixture {
	return &promotionFixture{state: executor.RolloutState{UID: "uid", ResourceVersion: "42", Phase: "Paused", PromotionRequired: true, PreviewReady: true}}
}

func promotionRequest(id uuid.UUID, role, body string, bind bool) *http.Request {
	req := httptest.NewRequest("POST", "/api/v1/deployments/"+id.String()+"/promote", strings.NewReader(body))
	req.SetPathValue("id", id.String())
	now := time.Now().Unix()
	claims := identity.Claims{Issuer: "frontend", Audience: "deployment", Subject: "reviewer", Role: role, Issued: now, Expiry: now + 25, Nonce: uuid.NewString()}
	if bind {
		sum := sha256.Sum256([]byte(body))
		claims.Body = hex.EncodeToString(sum[:])
	}
	return identity.WithClaims(req, claims)
}
func TestPromotionRequiresBodyBoundHumanAndReadyRevision(t *testing.T) {
	body := `{"uid":"uid","resource_version":"42","approve":true}`
	for _, scenario := range []string{"valid", "developer", "sre", "unbound", "wrong version", "unready", "uncertain", "replay"} {
		t.Run(scenario, func(t *testing.T) {
			f := readyPromotionFixture()
			h := RolloutHandler{Source: f, Store: f}
			role := "platform-engineer"
			bind := true
			requestBody := body
			want := 202
			switch scenario {
			case "developer", "sre":
				role = scenario
				want = 403
			case "unbound":
				bind = false
				want = 401
			case "wrong version":
				requestBody = strings.Replace(body, "42", "old", 1)
				want = 409
			case "unready":
				f.state.PreviewReady = false
				want = 409
			case "uncertain":
				f.patchErr = errors.New("lost response")
				want = 409
			}
			req := promotionRequest(uuid.New(), role, requestBody, bind)
			rec := httptest.NewRecorder()
			h.Promote(rec, req)
			if rec.Code != want {
				t.Fatalf("got %d: %s", rec.Code, rec.Body.String())
			}
			if want == 202 && f.patches != 1 {
				t.Fatal("approval not executed")
			}
			if want == 401 || want == 403 || scenario == "wrong version" || scenario == "unready" {
				if f.claims != 0 || f.patches != 0 {
					t.Fatal("invalid approval reached execution")
				}
			}
			if scenario == "uncertain" && (len(f.outcomes) != 1 || f.outcomes[0]) {
				t.Fatal("uncertain mutation not audited")
			}
			if scenario == "replay" {
				rec = httptest.NewRecorder()
				h.Promote(rec, promotionRequest(uuid.New(), role, body, true))
				if rec.Code != 409 || f.patches != 1 {
					t.Fatal("replayed approval executed")
				}
			}
		})
	}
}
func TestConcurrentPromotionClaimsExecuteOnce(t *testing.T) {
	f := readyPromotionFixture()
	h := RolloutHandler{Source: f, Store: f}
	var group sync.WaitGroup
	for range 8 {
		group.Add(1)
		go func() {
			defer group.Done()
			h.Promote(httptest.NewRecorder(), promotionRequest(uuid.New(), "platform-engineer", `{"uid":"uid","resource_version":"42","approve":true}`, true))
		}()
	}
	group.Wait()
	if f.patches != 1 {
		t.Fatal(f.patches)
	}
}
func TestDirectPromotionCannotUseForwardedRolesOrServiceIdentity(t *testing.T) {
	f := readyPromotionFixture()
	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/deployments/{id}/promote", (&RolloutHandler{Source: f, Store: f}).Promote)
	router := NewAuthenticatedRouter(mux, testFrontendKey, testAIOpsKey)
	for _, role := range []string{"", "developer", "sre"} {
		req := httptest.NewRequest("POST", "/api/v1/deployments/"+uuid.NewString()+"/promote", strings.NewReader(`{}`))
		req.Header.Set("X-CloudForge-Role", "platform-engineer")
		req.Header.Set("X-CloudForge-Actor", "reviewer")
		if role != "" {
			signDeploymentRequest(req, "frontend", testFrontendKey, role)
		}
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		if rec.Code != 401 && rec.Code != 403 {
			t.Fatal(rec.Code)
		}
	}
	if f.patches != 0 {
		t.Fatal("forged caller executed")
	}
}

func TestPromotionIdentityValidatesAudienceTargetExpirySignatureAndBody(t *testing.T) {
	fixture := readyPromotionFixture()
	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/deployments/{id}/promote", (&RolloutHandler{Source: fixture, Store: fixture}).Promote)
	router := NewAuthenticatedRouter(mux, testFrontendKey, testAIOpsKey)
	target := "/api/v1/deployments/" + uuid.NewString() + "/promote"
	body := `{"uid":"uid","resource_version":"42","approve":true}`
	for _, scenario := range []string{"wrong audience", "wrong target", "expired", "invalid signature", "wrong body", "valid", "replay"} {
		t.Run(scenario, func(t *testing.T) {
			req := httptest.NewRequest("POST", target, strings.NewReader(body))
			now := time.Now().Unix()
			hash := sha256.Sum256([]byte(body))
			claims := identity.Claims{Issuer: "frontend", Audience: "deployment", Subject: "reviewer", Role: "platform-engineer", Method: "POST", Target: target, Issued: now, Expiry: now + 25, Nonce: "0123456789abcdef0123456789abcdef", Body: hex.EncodeToString(hash[:])}
			switch scenario {
			case "wrong audience":
				claims.Audience = "infrastructure"
			case "wrong target":
				claims.Target = target + "?unbound=1"
			case "expired":
				claims.Issued = now - 30
				claims.Expiry = now - 1
			case "wrong body":
				claims.Body = strings.Repeat("0", 64)
			}
			signed := identity.Sign(claims, testFrontendKey)
			if scenario == "invalid signature" {
				signed += "x"
			}
			req.Header.Set(identity.Header, signed)
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, req)
			expected := 401
			if scenario == "valid" {
				expected = 202
			}
			if scenario == "replay" {
				expected = 409
			}
			if rec.Code != expected {
				t.Fatalf("got %d: %s", rec.Code, rec.Body.String())
			}
		})
	}
	if fixture.patches != 1 {
		t.Fatal("invalid or replayed identity reached mutation", fixture.patches)
	}
}
