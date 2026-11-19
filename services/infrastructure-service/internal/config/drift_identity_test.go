package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDriftIdentityFailsClosed(t *testing.T) {
	for _, key := range []string{"AWS_ROLE_ARN", "CLOUDFORGE_DRIFT_ROLE_ARN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_WEB_IDENTITY_TOKEN_FILE"} {
		t.Setenv(key, "")
	}
	if ValidateDriftIdentity() == nil {
		t.Fatal("missing workload identity accepted")
	}
	file := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(file, []byte("fixture-token-not-an-STS-authentication-test"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CLOUDFORGE_DRIFT_ROLE_ARN", "arn:aws:iam::123456789012:role/fixture-reader")
	t.Setenv("AWS_ROLE_ARN", os.Getenv("CLOUDFORGE_DRIFT_ROLE_ARN"))
	t.Setenv("AWS_WEB_IDENTITY_TOKEN_FILE", file)
	if err := ValidateDriftIdentity(); err != nil {
		t.Fatal(err)
	}
	t.Setenv("AWS_ACCESS_KEY_ID", "fixture-static-key")
	if ValidateDriftIdentity() == nil {
		t.Fatal("static key fallback accepted")
	}
}
