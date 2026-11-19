package handler

import (
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/service"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/terraform"
	identity "github.com/sufiyannadeem/cloudforge-service-identity"
)

type reviewScopeDB struct {
	project, level string
}

type reviewScopeRow func(...any) error

func (r reviewScopeRow) Scan(values ...any) error { return r(values...) }

func (db reviewScopeDB) QueryRow(_ context.Context, query string, args ...any) pgx.Row {
	return reviewScopeRow(func(values ...any) error {
		if strings.Contains(query, "FROM infrastructure_resources") {
			*values[0].(**string) = &db.project
			*values[1].(*string) = ""
			return nil
		}
		if args[0] != db.project {
			return pgx.ErrNoRows
		}
		*values[0].(*string) = db.level
		return nil
	})
}

func TestDeveloperReviewAndProjectLimits(t *testing.T) {
	project := uuid.NewString()
	const key = "infra-review-test-key-at-least-32-bytes"
	create := fmt.Sprintf(`{"project_id":%q,"name":"request","provider":"aws"}`, project)
	path := "/api/v1/resources/" + uuid.NewString()
	for _, tc := range []struct {
		path, body, level string
		status            int
	}{
		{"/api/v1/resources", create, "maintainer", 201},
		{"/api/v1/resources", create, "viewer", 403},
		{"/api/v1/resources", fmt.Sprintf(`{"project_id":%q}`, uuid.NewString()), "owner", 404},
		{path + "/review", `{"operation":"apply","action":"approve"}`, "maintainer", 403},
		{path + "/review", `{"operation":"apply","action":"reject"}`, "maintainer", 403},
		{path + "/review", `{"operation":"apply","action":"submit"}`, "viewer", 403},
		{path + "/apply", `{}`, "owner", 403},
		{path + "/drift", `{}`, "owner", 403},
		{path + "/destroy/plan", `{}`, "owner", 403},
		{path + "/destroy/apply", `{}`, "owner", 403},
	} {
		h := NewResourceHandler(&mockResourceManager{}, service.NewProvisioningService(nil, nil))
		router := NewAuthenticatedRouter(h, key, func(context.Context, identity.Claims) error { return nil },
			identity.ProjectAccess{DB: reviewScopeDB{project, tc.level}})
		req := httptest.NewRequest(http.MethodPost, tc.path, strings.NewReader(tc.body))
		now := time.Now().Unix()
		req.Header.Set(identity.Header, identity.Sign(identity.Claims{
			Issuer: "frontend", Audience: "infrastructure", Role: "developer", Subject: "developer",
			Method: req.Method, Target: req.URL.RequestURI(), Issued: now, Expiry: now + 25,
			Nonce: "0123456789abcdef0123456789abcdef", Body: fmt.Sprintf("%x", sha256.Sum256([]byte(tc.body))),
		}, key))
		req.Header.Set("X-CloudForge-Role", "platform-engineer")
		res := httptest.NewRecorder()
		router.ServeHTTP(res, req)
		if res.Code != tc.status {
			t.Errorf("%s as %s got %d want %d", tc.path, tc.level, res.Code, tc.status)
		}
	}
}

func TestSafePlanSummaryNeverReturnsValues(t *testing.T) {
	input := "value = \"credential\"\nPlan: 2 to add, 0 to change, 1 to destroy.\n"
	if got := terraform.PublicPlanSummary(input); got != "Plan: 2 to add, 0 to change, 1 to destroy." {
		t.Fatalf("unexpected safe summary: %q", got)
	}
	if got := terraform.PublicPlanSummary("no verified counts; arbitrary Terraform output"); got != "" {
		t.Fatal("unavailable summary must remain empty")
	}
}
