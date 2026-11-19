package terraform

import (
	"errors"
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
case "$*" in
  "apply "*destroy.tfplan) touch .test-destroyed ;;
esac
if [ "$1" = "show" ]; then
  if [ "$2" = "-json" ] && [ "$#" = 2 ]; then
    if [ -f .test-destroyed ]; then
      printf '%s\n' '{"format_version":"1.0"}'
    else
      printf '%s\n' '{"values":{"root_module":{"resources":[{"address":"aws_s3_bucket.this","mode":"managed","type":"aws_s3_bucket","provider_name":"registry.terraform.io/hashicorp/aws","values":{"id":"verified-test-bucket"}}]}}}'
    fi
  else
    echo "Plan: 1 to add, 0 to change, 0 to destroy."
  fi
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
	if got := calls[len(calls)-2]; got != "apply -input=false -lock=true -lock-timeout=5m -no-color destroy.tfplan" {
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
	if got := calls[len(calls)-3]; got != "apply -input=false -lock=true -lock-timeout=5m -no-color cloudforge.tfplan" {
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

func TestStructuredPlanSummaryOmitsValuesAndShowsReplacement(t *testing.T) {
	output := `{"resource_changes":[{"address":"aws_db_instance.private-name",
	  "type":"aws_db_instance","change":{"actions":["delete","create"],
	  "before":{"password":"old-secret"},"after":{"password":"new-secret"}}},
	  {"type":"aws_s3_bucket","change":{"actions":["create"]}}]}`
	want := "Create aws_s3_bucket: 1\nReplace aws_db_instance: 1"
	if got := summarizeTerraformPlan(output); got != want {
		t.Fatalf("structured summary = %q, want %q", got, want)
	}
}

func TestApplyRejectsSuccessfulExitWithoutVerifiedAWSState(t *testing.T) {
	runner, _ := testRunner(t, "")
	resource := testResource()
	result, err := runner.Plan(t.Context(), resource)
	if err != nil {
		t.Fatal(err)
	}
	resource.PlanPath, resource.PlanHash = result.PlanPath, result.PlanHash

	script, err := os.ReadFile(runner.TerraformBin)
	if err != nil {
		t.Fatal(err)
	}
	script = []byte(strings.Replace(string(script), "verified-test-bucket", "", 1))
	if err := os.WriteFile(runner.TerraformBin, script, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := runner.Apply(t.Context(), resource); err == nil || !strings.Contains(err.Error(), "could not be verified in state") {
		t.Fatalf("expected unverifiable-state error, got %v", err)
	}
}

func TestRemoteStateFailsClosedForUnboundAndChangedPlans(t *testing.T) {
	runner, logPath := testRunner(t, "")
	resource := testResource()
	local, err := runner.Plan(t.Context(), resource)
	if err != nil {
		t.Fatal(err)
	}
	runner.RequireRemoteState = true
	if _, err := runner.Plan(t.Context(), resource); err == nil {
		t.Fatal("remote-state runner accepted an empty bucket")
	}
	runner.Generator.StateBucket = "test-state-bucket"
	resource.PlanPath, resource.PlanHash = local.PlanPath, local.PlanHash
	if err := runner.Apply(t.Context(), resource); err == nil {
		t.Fatal("remote-state runner accepted a legacy local plan")
	}
	for _, call := range readLog(t, logPath) {
		if strings.HasPrefix(call, "apply ") {
			t.Fatal("unbound plan reached Terraform apply")
		}
	}
	remote, err := runner.Plan(t.Context(), resource)
	if err != nil {
		t.Fatal(err)
	}
	resource.PlanPath, resource.PlanHash = remote.PlanPath, remote.PlanHash
	if err := runner.Apply(t.Context(), resource); err != nil {
		t.Fatalf("bound plan did not execute: %v", err)
	}
	runner.Generator.StateBucket = "changed-state-bucket"
	if err := runner.Apply(t.Context(), resource); err == nil {
		t.Fatal("plan survived a change to the remote backend")
	}
}

func TestApplyRequiresSuccessfulProviderRefresh(t *testing.T) {
	runner, logPath := testRunner(t, "")
	resource := testResource()
	plan, err := runner.Plan(t.Context(), resource)
	if err != nil {
		t.Fatal(err)
	}
	resource.PlanPath, resource.PlanHash = plan.PlanPath, plan.PlanHash
	script := strings.Replace(string(mustReadFile(t, runner.TerraformBin)), "exit 0", `case "$*" in *-refresh-only*) echo private-output >&2; exit 2 ;; esac
exit 0`, 1)
	if err := os.WriteFile(runner.TerraformBin, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	id, err := runner.ApplyWithState(t.Context(), resource)
	if id != "verified-test-bucket" || err == nil || !strings.Contains(err.Error(), "reconciliation required") ||
		strings.Contains(err.Error(), "private-output") {
		t.Fatalf("provider drift did not retain the state ID safely: %q, %v", id, err)
	}
	calls := readLog(t, logPath)
	if got := calls[len(calls)-1]; got != "plan -input=false -no-color -refresh-only -detailed-exitcode -lock=false" {
		t.Fatalf("unexpected provider refresh: %s", got)
	}
}

func TestDestroyRejectsRemainingManagedResources(t *testing.T) {
	runner, _, resource := destroyPlanned(t)
	script := strings.Replace(string(mustReadFile(t, runner.TerraformBin)), "touch .test-destroyed", "true", 1)
	script = strings.Replace(script, `'{"values":`, `'{"format_version":"1.0","values":`, 1)
	if err := os.WriteFile(runner.TerraformBin, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := runner.ApplyDestroy(t.Context(), resource); err == nil || !strings.Contains(err.Error(), "empty managed state") {
		t.Fatalf("nonempty state reported as destroyed: %v", err)
	}
	if hasEmptyManagedState(`{"format_version":"1.0","values":{"root_module":{"child_modules":[{"resources":[{"mode":"managed"}]}]}}}`) {
		t.Fatal("child module resource counted as empty state")
	}
}

func TestPartialApplyReturnsObservedIDWithoutClaimingSuccess(t *testing.T) {
	runner, logPath := testRunner(t, "apply")
	resource := testResource()
	plan, err := runner.Plan(t.Context(), resource)
	if err != nil {
		t.Fatal(err)
	}
	resource.PlanPath, resource.PlanHash = plan.PlanPath, plan.PlanHash
	id, err := runner.ApplyWithState(t.Context(), resource)
	if id != "verified-test-bucket" || !errors.Is(err, errTerraformApplyExecution) {
		t.Fatalf("partial apply did not retain its evidence: %q, %v", id, err)
	}
	for _, call := range readLog(t, logPath) {
		if strings.Contains(call, "-refresh-only") {
			t.Fatal("partial apply continued into success verification")
		}
	}
}
