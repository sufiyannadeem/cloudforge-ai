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
	Generator    *Generator
	TerraformBin string
	PlanTimeout  time.Duration
	ApplyTimeout time.Duration
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

	workspace, err := r.Generator.Generate(resource)
	if err != nil {
		return PlanResult{}, err
	}

	fileName := planFileName
	planArgs := []string{
		"plan",
		"-input=false",
		"-no-color",
		"-lock-timeout=5m",
	}

	if destroy {
		fileName = destroyPlanFileName
		planArgs = append(planArgs, "-destroy")
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

	if err := r.run(
		planContext,
		workspace.Directory,
		"init",
		"-input=false",
		"-no-color",
	); err != nil {
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

	createdAt := time.Now().UTC()

	var summary string
	showOut, showErr := r.runWithOutput(
		planContext,
		workspace.Directory,
		"show",
		"-no-color",
		fileName,
	)
	if showErr == nil && strings.TrimSpace(showOut) != "" {
		summary = sanitizeTerraformOutput(showOut)
	} else {
		if destroy {
			summary = fmt.Sprintf("Terraform destroy plan: 1 to destroy (%s: %s)", resource.ResourceType, resource.Name)
		} else {
			summary = fmt.Sprintf("Terraform plan: 1 to add, 0 to change, 0 to destroy (%s: %s)", resource.ResourceType, resource.Name)
		}
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
	return r.apply(
		ctx,
		resource,
		resource.PlanPath,
		resource.PlanHash,
		planFileName,
	)
}

// ApplyDestroy verifies the approved destroy plan hash and then applies
// exactly that saved plan file; nothing is re-planned at apply time.
func (r *Runner) ApplyDestroy(
	ctx context.Context,
	resource model.InfrastructureResource,
) error {
	return r.apply(
		ctx,
		resource,
		resource.DestroyPlanPath,
		resource.DestroyPlanHash,
		destroyPlanFileName,
	)
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
		"-no-color",
		fileName,
	); err != nil {
		return fmt.Errorf(
			"terraform apply failed: %w",
			err,
		)
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

	command.Env = os.Environ()

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
		return string(data), nil
	}

	return r.runWithOutput(
		ctx,
		filepath.Dir(resource.PlanPath),
		"show",
		"-no-color",
		filepath.Base(resource.PlanPath),
	)
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
