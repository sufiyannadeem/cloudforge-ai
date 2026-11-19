package terraform

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/sufiyannadeem/cloudforge-ai-infrastructure-service/internal/model"
)

const (
	defaultPlanTimeout  = 10 * time.Minute
	defaultApplyTimeout = 30 * time.Minute

	planFileName = "cloudforge.tfplan"

	// destroyPlanFileName is kept separate from planFileName so a destroy
	// plan can never be applied through the create/update Apply path (and
	// vice versa).
	destroyPlanFileName = "destroy.tfplan"
)

var errTerraformApplyExecution = errors.New("terraform apply failed")

type Provisioner interface {
	Plan(
		ctx context.Context,
		resource model.InfrastructureResource,
	) (PlanResult, error)

	Apply(
		ctx context.Context,
		resource model.InfrastructureResource,
	) error

	// PlanDestroy produces a hashed `terraform plan -destroy` artifact.
	// It never mutates AWS.
	PlanDestroy(
		ctx context.Context,
		resource model.InfrastructureResource,
	) (PlanResult, error)

	// ApplyDestroy applies only the previously approved destroy plan whose
	// SHA-256 matches resource.DestroyPlanHash.
	ApplyDestroy(
		ctx context.Context,
		resource model.InfrastructureResource,
	) error
}

type PlanResult struct {
	WorkspaceDirectory string
	PlanPath           string
	PlanHash           string
	PlanCreatedAt      time.Time
	PlanSummary        string
}

type Runner struct {
	Generator          *Generator
	TerraformBin       string
	PlanTimeout        time.Duration
	ApplyTimeout       time.Duration
	RequireRemoteState bool
}

func NewRunner(
	generator *Generator,
) *Runner {
	return &Runner{
		Generator:    generator,
		TerraformBin: "terraform",
		PlanTimeout:  defaultPlanTimeout,
		ApplyTimeout: defaultApplyTimeout,
	}
}

func (r *Runner) Plan(
	ctx context.Context,
	resource model.InfrastructureResource,
) (PlanResult, error) {
	return r.plan(ctx, resource, false)
}

// PlanDestroy runs init, validate and `plan -destroy` in the resource
// workspace and returns the SHA-256 of destroy.tfplan for human approval.
func (r *Runner) PlanDestroy(
	ctx context.Context,
	resource model.InfrastructureResource,
) (PlanResult, error) {
	return r.plan(ctx, resource, true)
}

func (r *Runner) plan(
	ctx context.Context,
	resource model.InfrastructureResource,
	destroy bool,
) (PlanResult, error) {
	if r.Generator == nil {
		return PlanResult{}, errors.New(
			"terraform generator cannot be nil",
		)
	}

	if err := validateResourceForExecution(resource); err != nil {
		return PlanResult{}, err
	}

	if r.RequireRemoteState && r.Generator.StateBucket == "" {
		return PlanResult{}, errors.New("locked remote terraform state is required")
	}

	workspace, err := r.Generator.Generate(resource)
	if err != nil {
		return PlanResult{}, err
	}

	fileName := planFileName
	planArgs := []string{
		"plan",
		"-input=false",
		"-no-color",
		"-lock=true",
		"-lock-timeout=5m",
	}

	if destroy {
		fileName = destroyPlanFileName
		planArgs = append(planArgs, "-destroy", "-refresh=true")
	}

	planArgs = append(planArgs, "-out="+fileName)

	planPath := filepath.Join(
		workspace.Directory,
		fileName,
	)

	if err := removeIfExists(planPath); err != nil {
		return PlanResult{}, err
	}

	planContext, cancel := context.WithTimeout(
		ctx,
		r.planTimeout(),
	)
	defer cancel()

	initArgs := []string{"init", "-input=false", "-no-color"}
	if r.RequireRemoteState {
		initArgs = append(initArgs, "-backend=true")
	}
	if err := r.run(planContext, workspace.Directory, initArgs...); err != nil {
		return PlanResult{}, fmt.Errorf(
			"terraform init failed: %w",
			err,
		)
	}

	if err := r.run(
		planContext,
		workspace.Directory,
		"validate",
		"-no-color",
	); err != nil {
		return PlanResult{}, fmt.Errorf(
			"terraform validate failed: %w",
			err,
		)
	}

	if err := r.run(
		planContext,
		workspace.Directory,
		planArgs...,
	); err != nil {
		return PlanResult{}, fmt.Errorf(
			"terraform plan failed: %w",
			err,
		)
	}

	info, err := os.Stat(planPath)
	if err != nil {
		return PlanResult{}, fmt.Errorf(
			"terraform plan file was not created: %w",
			err,
		)
	}

	if info.Size() == 0 {
		return PlanResult{}, errors.New(
			"terraform generated an empty plan file",
		)
	}

	hash, err := hashFile(planPath)
	if err != nil {
		return PlanResult{}, err
	}

	if r.RequireRemoteState {
		if err := os.WriteFile(planPath+".remote", []byte(r.remotePlanBinding(resource, hash)), 0o600); err != nil {
			return PlanResult{}, errors.New("could not bind terraform plan to remote state")
		}
	}

	createdAt := time.Now().UTC()

	var summary string
	showOut, showErr := r.runWithOutput(
		planContext,
		workspace.Directory,
		"show",
		"-json",
		fileName,
	)
	if showErr == nil && strings.TrimSpace(showOut) != "" {
		summary = summarizeTerraformPlan(showOut)
	}

	summaryPath := planPath + ".summary"
	_ = os.WriteFile(summaryPath, []byte(summary), 0o600)

	return PlanResult{
		WorkspaceDirectory: workspace.Directory,
		PlanPath:           planPath,
		PlanHash:           hash,
		PlanCreatedAt:      createdAt,
		PlanSummary:        summary,
	}, nil
}

func (r *Runner) Apply(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	_, err := r.ApplyWithState(ctx, resource)
	return err
}

// ApplyWithState returns the provider ID observed in Terraform state, even if
// a subsequent provider refresh could not confirm that state.
func (r *Runner) ApplyWithState(ctx context.Context, resource model.InfrastructureResource) (string, error) {
	applyErr := r.apply(ctx, resource, resource.PlanPath, resource.PlanHash, planFileName)
	if applyErr != nil && !errors.Is(applyErr, errTerraformApplyExecution) {
		return "", applyErr
	}

	verifyCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 15*time.Second)
	defer cancel()
	state, err := r.runWithOutput(verifyCtx, filepath.Dir(resource.PlanPath), "show", "-json")
	id := provisionedResourceID(state, resource.ResourceType)
	if applyErr != nil {
		return id, applyErr
	}
	if err != nil || id == "" {
		return "", errors.New("terraform apply completed but the AWS resource could not be verified in state")
	}
	return id, r.verifyProviderRefresh(verifyCtx, filepath.Dir(resource.PlanPath))
}

// ApplyDestroy verifies the approved destroy plan hash and then applies
// exactly that saved plan file; nothing is re-planned at apply time.
func (r *Runner) ApplyDestroy(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	if err := r.apply(ctx, resource, resource.DestroyPlanPath, resource.DestroyPlanHash, destroyPlanFileName); err != nil {
		return err
	}
	verifyCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 15*time.Second)
	defer cancel()
	dir := filepath.Dir(resource.DestroyPlanPath)
	state, err := r.runWithOutput(verifyCtx, dir, "show", "-json")
	if err != nil || !hasEmptyManagedState(state) {
		return errors.New("terraform destroy completed but empty managed state could not be verified")
	}
	return nil
}

func (r *Runner) apply(
	ctx context.Context,
	resource model.InfrastructureResource,
	rawPlanPath string,
	approvedHash string,
	fileName string,
) error {
	if err := validateResourceForExecution(resource); err != nil {
		return err
	}

	if strings.TrimSpace(rawPlanPath) == "" {
		return errors.New(
			"terraform plan is required before apply",
		)
	}

	if strings.TrimSpace(approvedHash) == "" {
		return errors.New(
			"terraform plan hash is required before apply",
		)
	}

	planPath := filepath.Clean(rawPlanPath)

	if err := r.validatePlanPath(
		resource.ID,
		planPath,
		fileName,
	); err != nil {
		return err
	}

	if _, err := os.Stat(planPath); err != nil {
		return fmt.Errorf(
			"terraform plan file is unavailable: %w",
			err,
		)
	}

	actualHash, err := hashFile(planPath)
	if err != nil {
		return err
	}

	if !strings.EqualFold(
		actualHash,
		approvedHash,
	) {
		return errors.New(
			"terraform plan hash does not match approved plan",
		)
	}

	if r.RequireRemoteState {
		if r.Generator == nil || r.Generator.StateBucket == "" {
			return errors.New("locked remote terraform state is required")
		}
		binding, err := os.ReadFile(planPath + ".remote")
		backend, backendErr := os.ReadFile(filepath.Join(filepath.Dir(planPath), "backend.tf"))
		if err != nil || backendErr != nil || string(binding) != r.remotePlanBinding(resource, actualHash) ||
			string(backend) != r.Generator.backendFile(resource) {
			return errors.New("approved plan is missing its locked remote state binding; generate and approve a new plan")
		}
	}

	applyContext, cancel := context.WithTimeout(
		ctx,
		r.applyTimeout(),
	)
	defer cancel()

	if err := r.run(
		applyContext,
		filepath.Dir(planPath),
		"apply",
		"-input=false",
		"-lock=true",
		"-lock-timeout=5m",
		"-no-color",
		fileName,
	); err != nil {
		return fmt.Errorf("%w: %w", errTerraformApplyExecution, err)
	}

	return nil
}

func validateResourceForExecution(
	resource model.InfrastructureResource,
) error {
	if resource.ID == uuid.Nil {
		return errors.New(
			"resource ID cannot be empty",
		)
	}

	if resource.Provider != model.ProviderAWS {
		return errors.New(
			"only AWS resources are supported",
		)
	}

	switch resource.ResourceType {
	case resourceVPC, resourceEC2, resourceS3, resourceRDS, resourceEKS, resourceLB:
		return nil
	default:
		return fmt.Errorf(
			"unsupported resource type: %s",
			resource.ResourceType,
		)
	}
}

func (r *Runner) validatePlanPath(
	resourceID uuid.UUID,
	planPath string,
	fileName string,
) error {
	if resourceID == uuid.Nil {
		return errors.New(
			"resource ID cannot be empty",
		)
	}

	if filepath.Base(planPath) != fileName {
		return errors.New(
			"invalid terraform plan filename",
		)
	}

	if r.Generator == nil {
		return errors.New(
			"terraform generator cannot be nil",
		)
	}

	expectedWorkspace := filepath.Join(
		r.Generator.WorkspaceRoot,
		resourceID.String(),
	)

	expectedPlan := filepath.Join(
		expectedWorkspace,
		fileName,
	)

	if filepath.Clean(planPath) != filepath.Clean(expectedPlan) {
		return errors.New(
			"terraform plan path is outside the resource workspace",
		)
	}

	return nil
}

func (r *Runner) run(
	ctx context.Context,
	workspace string,
	args ...string,
) error {
	_, err := r.runWithOutput(ctx, workspace, args...)
	return err
}

func (r *Runner) runWithOutput(
	ctx context.Context,
	workspace string,
	args ...string,
) (string, error) {
	return r.runWithEnvironment(ctx, workspace, os.Environ(), args...)
}

func (r *Runner) runWithEnvironment(ctx context.Context, workspace string, environment []string, args ...string) (string, error) {
	if strings.TrimSpace(r.TerraformBin) == "" {
		return "", errors.New(
			"terraform binary cannot be empty",
		)
	}

	command := exec.CommandContext(
		ctx,
		r.TerraformBin,
		args...,
	)

	command.Dir = workspace

	command.Env = environment

	var stdout bytes.Buffer
	var stderr bytes.Buffer

	command.Stdout = &stdout
	command.Stderr = &stderr

	err := command.Run()

	if ctx.Err() != nil {
		return "", fmt.Errorf(
			"terraform command timed out or was cancelled: %w",
			ctx.Err(),
		)
	}

	if err != nil {
		return "", terraformCommandError(
			args,
			err,
			stderr.String(),
		)
	}

	return stdout.String(), nil
}

// ShowPlan reads the saved plan summary file or executes terraform show to inspect the plan.
func (r *Runner) ShowPlan(
	ctx context.Context,
	resource model.InfrastructureResource,
) (string, error) {
	if strings.TrimSpace(resource.PlanPath) == "" {
		return "", errors.New("terraform plan path is empty")
	}

	summaryPath := resource.PlanPath + ".summary"
	if data, err := os.ReadFile(summaryPath); err == nil && len(data) > 0 {
		return PublicPlanSummary(string(data)), nil
	}

	output, err := r.runWithOutput(
		ctx,
		filepath.Dir(resource.PlanPath),
		"show",
		"-json",
		filepath.Base(resource.PlanPath),
	)
	if err != nil {
		return "", errors.New("saved plan summary unavailable")
	}
	return summarizeTerraformPlan(output), nil
}

func terraformCommandError(
	args []string,
	err error,
	stderr string,
) error {
	command := strings.Join(args, " ")

	stderr = sanitizeTerraformOutput(stderr)

	if stderr == "" {
		return fmt.Errorf(
			"terraform command %q failed: %w",
			command,
			err,
		)
	}

	return fmt.Errorf(
		"terraform command %q failed: %w: %s",
		command,
		err,
		stderr,
	)
}

func sanitizeTerraformOutput(output string) string {
	lines := strings.Split(output, "\n")

	safeLines := make([]string, 0, len(lines))

	for _, line := range lines {
		lower := strings.ToLower(line)

		if strings.Contains(lower, "access_key") ||
			strings.Contains(lower, "secret_key") ||
			strings.Contains(lower, "session_token") ||
			strings.Contains(lower, "password") ||
			strings.Contains(lower, "authorization") {
			safeLines = append(
				safeLines,
				"[sensitive terraform output redacted]",
			)

			continue
		}

		safeLines = append(safeLines, line)
	}

	result := strings.TrimSpace(
		strings.Join(safeLines, "\n"),
	)

	const maxOutput = 4000

	if len(result) > maxOutput {
		return result[:maxOutput] +
			"\n[terraform output truncated]"
	}

	return result
}

func hashFile(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf(
			"open terraform plan for hashing: %w",
			err,
		)
	}
	defer file.Close()

	hasher := sha256.New()

	buffer := make([]byte, 128*1024)

	for {
		n, readErr := file.Read(buffer)

		if n > 0 {
			if _, err := hasher.Write(
				buffer[:n],
			); err != nil {
				return "", fmt.Errorf(
					"hash terraform plan: %w",
					err,
				)
			}
		}

		if errors.Is(readErr, os.ErrClosed) {
			return "", readErr
		}

		if readErr != nil {
			if errors.Is(
				readErr,
				context.Canceled,
			) {
				return "", readErr
			}

			break
		}
	}

	return hex.EncodeToString(
		hasher.Sum(nil),
	), nil
}

func removeIfExists(path string) error {
	err := os.Remove(path)

	if err == nil {
		return nil
	}

	if errors.Is(err, os.ErrNotExist) {
		return nil
	}

	return fmt.Errorf(
		"remove existing terraform plan: %w",
		err,
	)
}

func (r *Runner) planTimeout() time.Duration {
	if r.PlanTimeout <= 0 {
		return defaultPlanTimeout
	}

	return r.PlanTimeout
}

func (r *Runner) applyTimeout() time.Duration {
	if r.ApplyTimeout <= 0 {
		return defaultApplyTimeout
	}

	return r.ApplyTimeout
}

func (r *Runner) remotePlanBinding(resource model.InfrastructureResource, hash string) string {
	boundConfig := hash + "\n" + r.Generator.backendFile(resource)
	if r.Generator.ProvisionerRoleARN != "" {
		boundConfig += r.Generator.versionsFile()
	}
	binding := sha256.Sum256([]byte(boundConfig))
	return hex.EncodeToString(binding[:])
}

func (r *Runner) verifyProviderRefresh(ctx context.Context, workspace string) error {
	// Do not save or apply an observation plan, or create a remote lockfile.
	err := r.run(ctx, workspace, "plan", "-input=false", "-no-color", "-refresh-only", "-detailed-exitcode", "-lock=false")
	if err != nil {
		return errors.New("terraform apply completed but the provider refresh did not confirm the saved state; reconciliation required")
	}
	return nil
}
