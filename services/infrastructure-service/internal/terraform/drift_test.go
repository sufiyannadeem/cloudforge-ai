package terraform

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/google/uuid"
	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

func TestClassifyDriftSeparatesProviderAndDesiredEvidence(t *testing.T) {
	findings, err := classifyDrift(`{
		"format_version":"1.2","complete":true,
		"resource_drift":[{"mode":"managed","type":"aws_instance","change":{"actions":["delete"],"before":{"password":"secret"}}}],
		"resource_changes":[{"mode":"managed","type":"aws_instance","change":{"actions":["create"]}},
		{"mode":"managed","type":"aws_vpc","change":{"actions":["no-op"]}},
		{"mode":"data","type":"aws_ami","change":{"actions":["read"]}}]}`)
	if err != nil || len(findings) != 2 || findings[0].Source != "provider_drift" ||
		findings[0].Severity != "high" || findings[1].Source != "desired_change" {
		t.Fatalf("unexpected drift classification: %+v, %v", findings, err)
	}
}

func TestClassifyDriftRejectsUnavailableObservation(t *testing.T) {
	for _, raw := range []string{`{}`, `{"format_version":"1.2","complete":false}`, `{"format_version":"1.2","errored":true}`} {
		if _, err := classifyDrift(raw); err == nil {
			t.Errorf("accepted unavailable observation %s", raw)
		}
	}
}

func TestScanDriftUsesReadOnlyPlanInDisposableWorkspace(t *testing.T) {
	root := t.TempDir()
	binary := filepath.Join(root, "terraform")
	if err := os.WriteFile(binary, []byte(`#!/bin/sh
set -eu
test "$TF_WORKSPACE" = default
test -z "${TF_CLI_ARGS_plan-}"
test -z "${TF_DATA_DIR-}"
case "$PWD" in */cloudforge-drift-*/*) ;; *) exit 1 ;; esac
case "$1" in
 init) test "$*" = "init -input=false -no-color" ;;
 plan) case "$*" in *" -refresh=true -lock=false -out="*) ;; *) exit 1 ;; esac ;;
 show) printf '%s' '{"format_version":"1.2","complete":true}' ;;
 *) exit 1 ;;
esac
`), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TF_WORKSPACE", "other")
	t.Setenv("TF_DATA_DIR", root)
	t.Setenv("TF_CLI_ARGS_plan", "-lock=true")
	runner := &Runner{Generator: NewGenerator(root, "test-bucket"), TerraformBin: binary}
	resource := model.InfrastructureResource{ID: uuid.New(), Provider: model.ProviderAWS, ResourceType: resourceVPC,
		Region: "us-east-1", Name: "drift", Configuration: map[string]any{"cidr_block": "10.0.0.0/16"}}
	findings, err := runner.ScanDrift(context.Background(), resource)
	if err != nil || len(findings) != 0 {
		t.Fatalf("scan: %+v, %v", findings, err)
	}
	if _, err := os.Stat(filepath.Join(root, resource.ID.String())); !os.IsNotExist(err) {
		t.Fatalf("scan wrote to the provisioning workspace: %v", err)
	}
}
