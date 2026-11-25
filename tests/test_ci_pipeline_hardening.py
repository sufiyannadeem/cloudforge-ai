"""Tests for CloudForge AI CI/CD pipeline, security gates, and software supply-chain hardening."""

import os
import subprocess
import json
from pathlib import Path
import yaml
import pytest

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


def test_terraform_validate_bootstrap_and_dev(tmp_path):
    """Use only an explicitly supplied local provider mirror; never discover/download."""
    mirror = os.getenv("TF_OFFLINE_PROVIDER_MIRROR")
    if not mirror:
        pytest.skip("Offline Terraform provider mirror unavailable; native validation BLOCKED")
    mirror_path = Path(mirror).resolve()
    assert mirror_path.is_dir(), "Approved local provider mirror required"
    config = tmp_path / "terraform-offline.tfrc"
    config.write_text('provider_installation { filesystem_mirror { path = ' + json.dumps(str(mirror_path)) +
                      ' include = ["registry.terraform.io/*/*"] } }\n')
    env = dict(os.environ, TF_CLI_CONFIG_FILE=str(config))
    for directory in ["infrastructure/terraform/bootstrap", "infrastructure/terraform/environments/dev"]:
        res_init = subprocess.run(
            ["terraform", "init", "-backend=false", "-lockfile=readonly", "-input=false", "-get=false"],
            cwd=REPO_ROOT / directory, capture_output=True, text=True, env=env, timeout=60,
        )
        assert res_init.returncode == 0, f"Offline Terraform init failed in {directory}:\n{res_init.stderr}"
        res_val = subprocess.run(
            ["terraform", "validate"], cwd=REPO_ROOT / directory,
            capture_output=True, text=True, env=env, timeout=60,
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

    step = next(step for step in gate_job["steps"] if step.get("name") == "Gate evaluation")
    assert "python3" in step["run"] and "required_jobs" in step["run"]
    assert step["env"]["RESULTS"] == "${{ toJson(needs) }}"
    assert step["env"]["EVENT_NAME"] == "${{ github.event_name }}"
    assert step["env"]["COMMIT_MSG"] == "${{ github.event.head_commit.message }}"
    assert set(gate_job["needs"]) == {
        "security-gate-ci", "terraform-ci", "project-service-ci",
        "infrastructure-service-ci", "deployment-service-ci",
        "aiops-service-ci", "finops-service-ci", "frontend-ci",
    }


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
    """Execute the actual workflow shell step with simulated GitHub job results."""
    import json

    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    steps = [step for step in workflow["jobs"]["ci-gate"]["steps"]
             if step.get("name") == "Gate evaluation"]
    assert len(steps) == 1
    script = steps[0]["run"]

    env = os.environ.copy()
    env["EVENT_NAME"] = event_name
    env["COMMIT_MSG"] = commit_msg
    env["RESULTS"] = json.dumps(results)

    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
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
    assert "All CloudForge AI CI checks passed!" in res.stdout


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
    assert "All CloudForge AI CI checks passed!" not in res.stdout


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
    assert "All CloudForge AI CI checks passed!" not in res.stdout


@pytest.mark.parametrize("event,message,status,omit", [
    ("pull_request", "PR [skip ci]", "skipped", False),
    ("pull_request", "PR [ci skip]", "skipped", False),
    ("push", "Commit [skip ci]", "failure", False),
    ("pull_request", "Missing job result", "success", True),
])
def test_ci_gate_skip_markers_cannot_hide_required_checks(event, message, status, omit):
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    results = {job: {"result": "success"} for job in workflow["jobs"]["ci-gate"]["needs"]}
    if omit:
        del results["security-gate-ci"]
    else:
        results["security-gate-ci"]["result"] = status
    response = _run_gate_script(event, message, results)
    assert response.returncode != 0
    assert "security-gate-ci" in response.stdout
    assert "All CloudForge AI CI checks passed!" not in response.stdout


def test_security_image_builds_wire_local_shared_identity_context():
    security = yaml.safe_load((REPO_ROOT / '.github/workflows/security.yml').read_text())
    job = security['jobs']['image-security']
    entries = job['strategy']['matrix']['include']
    build = next(step for step in job['steps'] if step.get('uses', '').startswith('docker/build-push-action@'))
    assert build['with']['build-contexts'] == '${{ matrix.identity_context }}'
    for entry in entries:
        source = (REPO_ROOT / entry['dockerfile']).read_text()
        if 'COPY --from=service_identity' in source:
            assert entry['identity_context'] == 'service_identity=./services/service-identity'
            assert (REPO_ROOT / 'services/service-identity/go.mod').is_file()
        else:
            assert not entry.get('identity_context')
    assert build['with']['push'] is False


def test_security_trigger_scans_and_frontend_toolchain_match_release_policy():
    # BaseLoader retains the YAML 1.2 `on` key as a string (GitHub syntax).
    security = yaml.load((REPO_ROOT / '.github/workflows/security.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'feat/**' in security['on']['push']['branches']
    for filename in ['ci.yml', 'security.yml']:
        workflow = yaml.safe_load((REPO_ROOT / '.github/workflows' / filename).read_text())
        for job in workflow['jobs'].values():
            for step in job.get('steps', []):
                if not step.get('uses', '').startswith('aquasecurity/trivy-action@'):
                    continue
                settings = step['with']
                assert settings['version'] == 'v0.76.2'
                assert settings.get('ignore-unfixed') is not True
                if settings.get('exit-code') == '1' and settings.get('scan-type') in ['fs','config'] and settings.get('scan-ref') == '.':
                    assert settings['trivyignores'] == 'deploy/kubernetes/trivy-rbac-exceptions.yaml'
    ci = yaml.safe_load((REPO_ROOT / '.github/workflows/ci.yml').read_text())
    node = next(step for step in ci['jobs']['frontend-ci']['steps'] if step.get('uses', '').startswith('actions/setup-node@'))
    assert node['with']['node-version'] == 22


def test_python_ci_installs_only_hash_locked_wheels():
    data=yaml.safe_load((REPO_ROOT/'.github/workflows/ci.yml').read_text())
    for name in ['aiops-service-ci','finops-service-ci']:
        step=next(s for s in data['jobs'][name]['steps'] if s.get('name')=='Install locked dependencies')
        commands=step['run'].splitlines()
        assert len(commands)==2
        assert all('--only-binary=:all:' in cmd and '--require-hashes' in cmd for cmd in commands)
        assert '../../tests/requirements-ci.lock' in commands[1]
    lock=(REPO_ROOT/'tests/requirements-ci.lock').read_text()
    import re
    entries=[line for line in lock.splitlines() if line and not line.startswith('#')]
    assert len(entries)==5
    assert all(re.fullmatch(r'[a-z]+==[0-9.]+ --hash=sha256:[a-f0-9]{64}', line) for line in entries)


def test_frontend_ci_cannot_run_dependency_install_hooks_or_fetch_npx_tools():
    data=yaml.safe_load((REPO_ROOT/'.github/workflows/ci.yml').read_text())
    steps=data['jobs']['frontend-ci']['steps']
    assert next(s for s in steps if s.get('name')=='Install dependencies')['run']=='npm ci --ignore-scripts'
    assert next(s for s in steps if s.get('name')=='Run TypeScript typecheck')['run']=='./node_modules/.bin/tsc --noEmit'
    assert 'RUN npm ci --ignore-scripts' in (REPO_ROOT/'frontend/Dockerfile').read_text()
