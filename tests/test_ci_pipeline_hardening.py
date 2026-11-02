"""Tests for CloudForge AI CI/CD pipeline, security gates, and software supply-chain hardening."""

import os
import subprocess
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_ci_workflow_valid_structure():
    """Verify that .github/workflows/ci.yml exists and has proper jobs and gate definitions."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), "ci.yml must exist"

    with open(ci_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data.get("name") == "CloudForge AI CI"
    assert "jobs" in data

    expected_jobs = {
        "security-gate-ci",
        "terraform-ci",
        "project-service-ci",
        "infrastructure-service-ci",
        "deployment-service-ci",
        "aiops-service-ci",
        "finops-service-ci",
        "frontend-ci",
        "ci-gate",
    }
    actual_jobs = set(data["jobs"].keys())
    assert expected_jobs.issubset(actual_jobs), f"Missing jobs in CI workflow: {expected_jobs - actual_jobs}"

    # Verify ci-gate dependencies
    gate_needs = set(data["jobs"]["ci-gate"]["needs"])
    for job in expected_jobs - {"ci-gate"}:
        assert job in gate_needs, f"ci-gate must depend on {job}"


def test_ci_commit_loop_protection():
    """Verify that CI workflows prevent automated Git commit loops."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    with open(ci_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Permissions must be read-only at workflow level
    assert "permissions:\n  contents: read" in content or "permissions:\n    contents: read" in content

    # Checkouts must have persist-credentials: false
    assert "persist-credentials: false" in content

    # Automated commit message skip condition present
    assert "[skip ci]" in content and "[ci skip]" in content


def test_security_workflow_matrix_coverage():
    """Verify that security.yml scans all 6 services with proper failure gates."""
    sec_path = REPO_ROOT / ".github" / "workflows" / "security.yml"
    assert sec_path.exists(), "security.yml must exist"

    with open(sec_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    matrix_includes = data["jobs"]["image-security"]["strategy"]["matrix"]["include"]
    scanned_services = {item["name"] for item in matrix_includes}

    expected_services = {
        "project-service",
        "infrastructure-service",
        "deployment-service",
        "aiops-service",
        "finops-service",
        "frontend",
    }
    assert expected_services == scanned_services, f"Expected {expected_services}, found {scanned_services}"

    # Verify failure gates (exit-code 1)
    with open(sec_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'exit-code: "1"' in content


def test_artifact_traceability_tags_and_labels():
    """Verify that Docker builds apply traceable commit SHA tags and OCI labels."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    sec_path = REPO_ROOT / ".github" / "workflows" / "security.yml"

    for path in [ci_path, sec_path]:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "${{ github.sha }}" in content, f"Traceable git SHA tag missing in {path.name}"
        assert "org.opencontainers.image.revision" in content, f"OCI revision label missing in {path.name}"


def test_terraform_formatting():
    """Verify that Terraform configurations are properly formatted."""
    res = subprocess.run(
        ["terraform", "fmt", "-check", "-recursive", "infrastructure/terraform"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Unformatted Terraform files detected:\n{res.stdout}"


def test_terraform_validate_bootstrap_and_dev():
    """Verify that Terraform bootstrap and dev environments validate cleanly."""
    for directory in ["infrastructure/terraform/bootstrap", "infrastructure/terraform/environments/dev"]:
        res_init = subprocess.run(
            ["terraform", "init", "-backend=false"],
            cwd=REPO_ROOT / directory,
            capture_output=True,
            text=True,
        )
        assert res_init.returncode == 0, f"Terraform init failed in {directory}:\n{res_init.stderr}"

        res_val = subprocess.run(
            ["terraform", "validate"],
            cwd=REPO_ROOT / directory,
            capture_output=True,
            text=True,
        )
        assert res_val.returncode == 0, f"Terraform validate failed in {directory}:\n{res_val.stderr}"


def test_trivy_ignore_justification_documentation():
    """Verify that .trivyignore documents justifications for any excluded rules."""
    trivyignore_path = REPO_ROOT / ".trivyignore"
    assert trivyignore_path.exists(), ".trivyignore must exist"

    with open(trivyignore_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Ensure comments containing justifications exist before ignored rules
    has_justification = any(line.startswith("#") and "justification" in line.lower() for line in lines)
    assert has_justification, ".trivyignore must contain documented justifications"


def test_gitleaks_secret_scan():
    """Verify that Gitleaks detects zero secrets in the repository."""
    gitleaks_toml = REPO_ROOT / ".gitleaks.toml"
    assert gitleaks_toml.exists(), ".gitleaks.toml must exist"

    res = subprocess.run(
        ["gitleaks", "detect", "--config=.gitleaks.toml", "--no-banner"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Gitleaks detected secret leak:\n{res.stdout}\n{res.stderr}"


def test_gitignore_protects_credentials():
    """Verify that .gitignore excludes local environment, state, and credential files."""
    gitignore_path = REPO_ROOT / ".gitignore"
    assert gitignore_path.exists()

    with open(gitignore_path, "r", encoding="utf-8") as f:
        ignored = {line.strip() for line in f if line.strip() and not line.startswith("#")}

    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "*.tfstate" in ignored
    assert "*.key" in ignored
    assert "*.pem" in ignored


def test_ci_gate_uses_always_and_evaluates_results():
    """Verify that ci-gate uses if: always() and evaluates all required job results."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    with open(ci_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    gate_job = data["jobs"]["ci-gate"]
    assert gate_job.get("if") == "always()", "ci-gate must specify if: always()"

    # Ensure python evaluation step exists
    step_runs = [step.get("run", "") for step in gate_job.get("steps", [])]
    assert any("python3 -c" in run and "required_jobs" in run for run in step_runs), (
        "ci-gate must contain an explicit result evaluation step"
    )


def test_ci_jobs_event_aware_guardrails():
    """Verify that all CI jobs use event-aware skip conditions that protect PRs."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    with open(ci_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Check each job (except the gate which uses always())
    for name, job in data["jobs"].items():
        if name == "ci-gate":
            continue
        job_if = job.get("if", "")
        assert "github.event_name != 'push'" in job_if or "github.event_name == 'pull_request'" in job_if, (
            f"Job {name} must have event-aware skip condition protecting pull requests"
        )
        assert "[skip ci]" in job_if and "[ci skip]" in job_if, (
            f"Job {name} must support intentional skip on push"
        )


def _run_gate_script(event_name: str, commit_msg: str, results: dict) -> subprocess.CompletedProcess:
    """Helper to run the ci-gate evaluation script extracted from ci.yml with simulated inputs."""
    import json
    import textwrap

    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    with open(ci_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the python script from the ci-gate step textwrap block
    marker_start = "exec(textwrap.dedent('''"
    idx_start = content.find(marker_start)
    assert idx_start != -1, "Python evaluation script marker not found in ci.yml"
    idx_script = idx_start + len(marker_start)
    idx_end = content.find("'''))\"", idx_script)
    script = textwrap.dedent(content[idx_script:idx_end])

    env = os.environ.copy()
    env["EVENT_NAME"] = event_name
    env["COMMIT_MSG"] = commit_msg
    env["RESULTS"] = json.dumps(results)

    return subprocess.run(
        ["python3", "-c", script],
        env=env,
        capture_output=True,
        text=True,
    )


def test_ci_gate_all_passed():
    """Gate succeeds and emits success banner when all 8 required jobs pass."""
    required = [
        "security-gate-ci",
        "terraform-ci",
        "project-service-ci",
        "infrastructure-service-ci",
        "deployment-service-ci",
        "aiops-service-ci",
        "finops-service-ci",
        "frontend-ci",
    ]
    results = {job: {"result": "success"} for job in required}

    res = _run_gate_script("pull_request", "Merge feature", results)
    assert res.returncode == 0, f"Expected success, got {res.returncode}:\n{res.stderr}"
    assert "All CloudForge AI security gates, Terraform IaC" in res.stdout


def test_ci_gate_job_failure_detected():
    """Gate fails and identifies specific failed job."""
    required = [
        "security-gate-ci",
        "terraform-ci",
        "project-service-ci",
        "infrastructure-service-ci",
        "deployment-service-ci",
        "aiops-service-ci",
        "finops-service-ci",
        "frontend-ci",
    ]
    results = {job: {"result": "success"} for job in required}
    results["terraform-ci"]["result"] = "failure"

    res = _run_gate_script("pull_request", "Test PR", results)
    assert res.returncode != 0, "Gate must fail when dependency fails"
    assert "terraform-ci (status: failure)" in res.stdout
    assert "All CloudForge AI security gates" not in res.stdout


def test_ci_gate_job_cancelled_detected():
    """Gate fails when a dependency is cancelled."""
    required = [
        "security-gate-ci",
        "terraform-ci",
        "project-service-ci",
        "infrastructure-service-ci",
        "deployment-service-ci",
        "aiops-service-ci",
        "finops-service-ci",
        "frontend-ci",
    ]
    results = {job: {"result": "success"} for job in required}
    results["deployment-service-ci"]["result"] = "cancelled"

    res = _run_gate_script("push", "Regular commit", results)
    assert res.returncode != 0, "Gate must fail when dependency is cancelled"
    assert "deployment-service-ci (status: cancelled)" in res.stdout


def test_ci_gate_unexpected_skipped_detected():
    """Gate fails when a job is unexpectedly skipped on a standard push."""
    required = [
        "security-gate-ci",
        "terraform-ci",
        "project-service-ci",
        "infrastructure-service-ci",
        "deployment-service-ci",
        "aiops-service-ci",
        "finops-service-ci",
        "frontend-ci",
    ]
    results = {job: {"result": "success"} for job in required}
    results["security-gate-ci"]["result"] = "skipped"

    # Standard push with no [skip ci]
    res = _run_gate_script("push", "feat: add feature", results)
    assert res.returncode != 0, "Gate must fail when job is unexpectedly skipped"
    assert "unexpectedly skipped" in res.stdout
    assert "security-gate-ci" in res.stdout


def test_ci_gate_intentional_skip_handled_cleanly():
    """Gate exits cleanly without false success message when intentional skip is signaled on push."""
    required = [
        "security-gate-ci",
        "terraform-ci",
        "project-service-ci",
        "infrastructure-service-ci",
        "deployment-service-ci",
        "aiops-service-ci",
        "finops-service-ci",
        "frontend-ci",
    ]
    results = {job: {"result": "skipped"} for job in required}

    res = _run_gate_script("push", "docs: update notes [skip ci]", results)
    assert res.returncode == 0, "Gate should exit 0 on intentional skip"
    assert "intentionally skipped" in res.stdout
    assert "All CloudForge AI security gates" not in res.stdout
