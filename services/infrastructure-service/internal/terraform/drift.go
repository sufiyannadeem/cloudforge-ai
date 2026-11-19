package terraform

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

type DriftFinding struct {
	Address        string `json:"address,omitempty"`
	Type           string `json:"type"`
	Source         string `json:"source"`
	Severity       string `json:"severity"`
	Risk           string `json:"risk"`
	Recommendation string `json:"recommendation"`
}

// ScanDrift saves an observation plan only in a private, disposable workspace.
// A normal refreshed plan reports both external drift and desired configuration changes.
func (r *Runner) ScanDrift(ctx context.Context, resource model.InfrastructureResource) ([]DriftFinding, error) {
	if r.Generator == nil || r.Generator.StateBucket == "" {
		return nil, errors.New("remote state is required for drift scanning")
	}
	if err := validateResourceForExecution(resource); err != nil {
		return nil, err
	}
	root, err := os.MkdirTemp("", "cloudforge-drift-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(root)
	generator := *r.Generator
	generator.WorkspaceRoot = root
	workspace, err := generator.Generate(resource)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(ctx, r.planTimeout())
	defer cancel()
	environment := []string{"TF_WORKSPACE=default"}
	for _, entry := range os.Environ() {
		key, _, _ := strings.Cut(entry, "=")
		if key != "TF_DATA_DIR" && key != "TF_WORKSPACE" && key != "TF_CLI_ARGS" && !strings.HasPrefix(key, "TF_CLI_ARGS_") {
			environment = append(environment, entry)
		}
	}
	run := func(args ...string) (string, error) {
		return r.runWithEnvironment(ctx, workspace.Directory, environment, args...)
	}
	if _, err := run("init", "-input=false", "-no-color"); err != nil {
		return nil, err
	}
	// Avoid writing a remote lockfile. The service checks the resource revision
	// before recording evidence, since concurrent provisioning invalidates a scan.
	plan := filepath.Join(workspace.Directory, "observation.tfplan")
	if _, err := run("plan", "-input=false", "-no-color", "-refresh=true", "-lock=false", "-out="+plan); err != nil {
		return nil, err
	}
	raw, err := run("show", "-json", plan)
	if err != nil {
		return nil, err
	}
	return classifyDrift(raw)
}

var (
	safeResourceType    = regexp.MustCompile(`^aws_[a-z0-9_]{1,100}$`)
	safeResourceAddress = regexp.MustCompile(`^aws_[a-z0-9_]{1,100}\.[a-zA-Z0-9_]{1,100}(\[[0-9]+\])?$`)
)

func classifyDrift(raw string) ([]DriftFinding, error) {
	type change struct {
		Address string
		Type    string
		Mode    string
		Change  struct{ Actions []string }
	}
	var plan struct {
		Format   string `json:"format_version"`
		Errored  bool
		Complete *bool
		Drift    []change `json:"resource_drift"`
		Changes  []change `json:"resource_changes"`
	}
	if err := json.Unmarshal([]byte(raw), &plan); err != nil || len(plan.Format) < 2 || plan.Format[:2] != "1." || plan.Errored || (plan.Complete != nil && !*plan.Complete) {
		return nil, errors.New("Terraform observation is invalid or incomplete")
	}
	findings := []DriftFinding{}
	for _, group := range []struct {
		source  string
		changes []change
	}{{"provider_drift", plan.Drift}, {"desired_change", plan.Changes}} {
		for _, change := range group.changes {
			if change.Mode != "managed" || !safeResourceType.MatchString(change.Type) {
				continue
			}
			finding := DriftFinding{Type: change.Type, Source: group.source,
				Recommendation: "Review provider changes, then generate a fresh plan for Platform Engineer approval."}
			if safeResourceAddress.MatchString(change.Address) {
				finding.Address = change.Address
			}
			for _, action := range change.Change.Actions {
				switch action {
				case "delete":
					finding.Severity, finding.Risk = "high", "Resource removal or replacement may disrupt service or lose data."
				case "create", "update":
					if finding.Severity == "" {
						finding.Severity, finding.Risk = "medium", "Configuration divergence may affect security, availability, or cost."
					}
				}
			}
			if finding.Severity != "" {
				findings = append(findings, finding)
			}
		}
	}
	return findings, nil
}
