package terraform

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

// fakeTerraform writes a shell script that records its arguments and creates
// the file named by -out=, so runner behaviour can be tested without AWS.
func fakeTerraform(t *testing.T, failOn string) (bin string, logPath string) {
	t.Helper()

	if runtime.GOOS == "windows" {
		t.Skip("shell based fake terraform is not supported on windows")
	}

	dir := t.TempDir()
	logPath = filepath.Join(dir, "calls.log")
	bin = filepath.Join(dir, "terraform")

	script := `#!/bin/sh
echo "$@" >> "` + logPath + `"
if [ -n "` + failOn + `" ] && [ "$1" = "` + failOn + `" ]; then
  echo "simulated failure" >&2
  exit 1
fi
for arg in "$@"; do
  case "$arg" in
    -out=*) printf 'plan-for:%s' "$*" > "${arg#-out=}" ;;
  esac
done
if [ "$1" = "show" ]; then
  echo "Plan: 1 to add, 0 to change, 0 to destroy."
fi
exit 0
`
	if err := os.WriteFile(bin, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}

	return bin, logPath
}

func testRunner(t *testing.T, failOn string) (*Runner, string) {
	t.Helper()

	bin, logPath := fakeTerraform(t, failOn)
	runner := NewRunner(NewGenerator(t.TempDir(), ""))
	runner.TerraformBin = bin

	return runner, logPath
}

func testResource() model.InfrastructureResource {
	return model.InfrastructureResource{
		ID:           uuid.New(),
		Name:         "Test Bucket",
		Provider:     model.ProviderAWS,
		Region:       "eu-west-1",
		ResourceType: "aws_s3",
		Status:       model.ResourceStatusActive,
		Configuration: map[string]any{
			"bucket": "cloudforge-test-example",
		},
	}
}

func readLog(t *testing.T, path string) []string {
	t.Helper()

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}

	return strings.Split(strings.TrimSpace(string(data)), "\n")
}

func TestPlanDestroyProducesHashedDestroyPlan(t *testing.T) {
	runner, logPath := testRunner(t, "")
	resource := testResource()

	result, err := runner.PlanDestroy(t.Context(), resource)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if filepath.Base(result.PlanPath) != "destroy.tfplan" {
		t.Fatalf("expected destroy.tfplan, got %s", result.PlanPath)
	}
	if result.PlanCreatedAt.IsZero() {
		t.Fatal("expected creation timestamp")
	}

	want, err := hashFile(result.PlanPath)
	if err != nil || result.PlanHash != want || len(want) != 64 {
		t.Fatalf("hash mismatch: got %q want %q err=%v", result.PlanHash, want, err)
	}

	calls := readLog(t, logPath)
	var planCall string
	for _, call := range calls {
		if strings.HasPrefix(call, "plan ") {
			planCall = call
			break
		}
	}
	if planCall == "" {
		t.Fatal("expected terraform plan call in log")
	}
	for _, flag := range []string{"plan", "-destroy", "-input=false", "-no-color", "-out=destroy.tfplan"} {
		if !strings.Contains(planCall, flag) {
			t.Fatalf("plan call %q missing %s", planCall, flag)
		}
	}
	for _, call := range calls {
		if strings.HasPrefix(call, "apply") {
			t.Fatal("PlanDestroy must never run terraform apply")
		}
	}
}

func TestPlanDestroyFailureIsReported(t *testing.T) {
	runner, _ := testRunner(t, "plan")

	if _, err := runner.PlanDestroy(t.Context(), testResource()); err == nil ||
		!strings.Contains(err.Error(), "terraform plan failed") {
		t.Fatalf("expected plan failure, got %v", err)
	}
}

func TestPlanDestroyRejectsUnsupportedResource(t *testing.T) {
	runner, _ := testRunner(t, "")
	resource := testResource()
	resource.ResourceType = "aws_lambda"

	if _, err := runner.PlanDestroy(t.Context(), resource); err == nil {
		t.Fatal("expected unsupported resource error")
	}
}

func destroyPlanned(t *testing.T) (*Runner, string, model.InfrastructureResource) {
	t.Helper()

	runner, logPath := testRunner(t, "")
	resource := testResource()

	result, err := runner.PlanDestroy(t.Context(), resource)
	if err != nil {
		t.Fatal(err)
	}

	resource.DestroyPlanPath = result.PlanPath
	resource.DestroyPlanHash = result.PlanHash

	return runner, logPath, resource
}

func TestApplyDestroyAppliesApprovedPlan(t *testing.T) {
	runner, logPath, resource := destroyPlanned(t)

	if err := runner.ApplyDestroy(t.Context(), resource); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	calls := readLog(t, logPath)
	if got := calls[len(calls)-1]; got != "apply -input=false -no-color destroy.tfplan" {
		t.Fatalf("unexpected apply call %q", got)
	}
}

func TestApplyDestroyRejectsHashMismatch(t *testing.T) {
	runner, logPath, resource := destroyPlanned(t)
	resource.DestroyPlanHash = strings.Repeat("0", 64)

	err := runner.ApplyDestroy(t.Context(), resource)
	if err == nil || !strings.Contains(err.Error(), "hash does not match") {
		t.Fatalf("expected hash mismatch, got %v", err)
	}

	for _, call := range readLog(t, logPath) {
		if strings.HasPrefix(call, "apply") {
			t.Fatal("terraform apply must not run on hash mismatch")
		}
	}
}

func TestApplyDestroyRejectsTamperedPlan(t *testing.T) {
	runner, _, resource := destroyPlanned(t)

	if err := os.WriteFile(resource.DestroyPlanPath, []byte("tampered"), 0o600); err != nil {
		t.Fatal(err)
	}

	if err := runner.ApplyDestroy(t.Context(), resource); err == nil {
		t.Fatal("expected tampered plan to be rejected")
	}
}

func TestApplyDestroyRequiresPlanAndHash(t *testing.T) {
	runner, _, resource := destroyPlanned(t)

	noPath := resource
	noPath.DestroyPlanPath = ""
	if err := runner.ApplyDestroy(t.Context(), noPath); err == nil {
		t.Fatal("expected error without plan path")
	}

	noHash := resource
	noHash.DestroyPlanHash = ""
	if err := runner.ApplyDestroy(t.Context(), noHash); err == nil {
		t.Fatal("expected error without plan hash")
	}
}

func TestApplyDestroyRejectsPathOutsideWorkspace(t *testing.T) {
	runner, _, resource := destroyPlanned(t)

	outside := filepath.Join(t.TempDir(), "destroy.tfplan")
	if err := os.WriteFile(outside, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	resource.DestroyPlanPath = outside

	if err := runner.ApplyDestroy(t.Context(), resource); err == nil ||
		!strings.Contains(err.Error(), "outside the resource workspace") {
		t.Fatalf("expected outside-workspace error, got %v", err)
	}
}

func TestApplyDestroyRejectsCreatePlanFile(t *testing.T) {
	runner, _, resource := destroyPlanned(t)

	// A create plan must not be usable through the destroy path.
	resource.DestroyPlanPath = filepath.Join(filepath.Dir(resource.DestroyPlanPath), planFileName)

	if err := runner.ApplyDestroy(t.Context(), resource); err == nil ||
		!strings.Contains(err.Error(), "invalid terraform plan filename") {
		t.Fatalf("expected filename rejection, got %v", err)
	}
}

func TestApplyDestroyFailureIsReported(t *testing.T) {
	runner, _, resource := destroyPlanned(t)
	failing, _ := fakeTerraform(t, "apply")
	runner.TerraformBin = failing

	if err := runner.ApplyDestroy(t.Context(), resource); err == nil ||
		!strings.Contains(err.Error(), "terraform apply failed") {
		t.Fatalf("expected apply failure, got %v", err)
	}
}

func TestApplyStillUsesCreatePlanFile(t *testing.T) {
	runner, logPath := testRunner(t, "")
	resource := testResource()

	result, err := runner.Plan(t.Context(), resource)
	if err != nil {
		t.Fatal(err)
	}
	resource.PlanPath, resource.PlanHash = result.PlanPath, result.PlanHash

	if err := runner.Apply(t.Context(), resource); err != nil {
		t.Fatal(err)
	}

	calls := readLog(t, logPath)
	if got := calls[len(calls)-1]; got != "apply -input=false -no-color cloudforge.tfplan" {
		t.Fatalf("unexpected apply call %q", got)
	}
	for _, call := range calls {
		if strings.Contains(call, "-destroy") {
			t.Fatal("create plan must not use -destroy")
		}
	}
}

func TestPlanProducesSummary(t *testing.T) {
	runner, _ := testRunner(t, "")
	resource := testResource()

	result, err := runner.Plan(t.Context(), resource)
	if err != nil {
		t.Fatalf("unexpected plan error: %v", err)
	}

	if result.PlanSummary == "" {
		t.Fatal("expected non-empty plan summary")
	}

	summaryFile := result.PlanPath + ".summary"
	data, err := os.ReadFile(summaryFile)
	if err != nil {
		t.Fatalf("read plan summary file: %v", err)
	}
	if string(data) != result.PlanSummary {
		t.Fatalf("summary file content mismatch: got %q, want %q", string(data), result.PlanSummary)
	}

	resource.PlanPath = result.PlanPath
	showSummary, err := runner.ShowPlan(t.Context(), resource)
	if err != nil {
		t.Fatalf("ShowPlan error: %v", err)
	}
	if showSummary != result.PlanSummary {
		t.Fatalf("ShowPlan mismatch: got %q, want %q", showSummary, result.PlanSummary)
	}
}
