package config

import (
	"errors"
	"os"
)

// Scheduled readers never inherit a node identity or static provisioner keys.
// STS still validates the projected token and target-role trust at execution.
func ValidateDriftIdentity() error {
	expected := os.Getenv("CLOUDFORGE_DRIFT_ROLE_ARN")
	if expected == "" || os.Getenv("AWS_ROLE_ARN") != expected || os.Getenv("AWS_ACCESS_KEY_ID") != "" || os.Getenv("AWS_SECRET_ACCESS_KEY") != "" {
		return errors.New("scheduled drift requires its dedicated projected workload identity")
	}
	info, err := os.Stat(os.Getenv("AWS_WEB_IDENTITY_TOKEN_FILE"))
	if err != nil || !info.Mode().IsRegular() || info.Size() == 0 {
		return errors.New("scheduled drift workload token unavailable")
	}
	return nil
}
