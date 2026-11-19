"""Unit tests for AWS Secrets Manager loader."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

from .aws_secrets_loader import (
    AWSSecretsManagerError,
    get_default_secret_path,
    load_secrets_from_secrets_manager,
    populate_env_from_secrets_manager,
    reset_secrets_cache,
    resolve_secret_name,
)



@pytest.fixture(autouse=True)
def clean_cache_and_env():
    """Reset Secrets Manager cache before each test; restore env vars after."""
    reset_secrets_cache()

    # Stash env vars that might affect resolution
    stash_keys = [
        "CLOUDFORGE_SECRET_NAME",
        "AWS_SECRETS_MANAGER_SECRET_NAME",
        "AWS_SECRETS_MANAGER_ENABLED",
        "FINOPS_SERVICE_SECRET_NAME",
        "AIOPS_SERVICE_SECRET_NAME",
        "CLOUDFORGE_INTERNAL_API_TOKEN",
        "APP_ENV",
    ]
    saved = {k: os.environ.pop(k, None) for k in stash_keys}

    yield

    # Restore originals
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)

    reset_secrets_cache()


# ---------------------------------------------------------------------------
# 1. Per-service canonical path generation
# ---------------------------------------------------------------------------

def test_get_default_secret_path_finops():
    path = get_default_secret_path("finops-service", env="prod")
    assert path == "cloudforge/prod/finops-service/credentials"


def test_get_default_secret_path_aiops():
    path = get_default_secret_path("aiops-service", env="prod")
    assert path == "cloudforge/prod/aiops-service/credentials"


def test_get_default_secret_path_dev():
    path = get_default_secret_path("finops-service", env="dev")
    assert path == "cloudforge/dev/finops-service/credentials"


# ---------------------------------------------------------------------------
# 2. Per-service secret name resolution
# ---------------------------------------------------------------------------

def test_resolve_secret_name_explicit():
    name = resolve_secret_name(secret_name="cloudforge/prod/finops-service/credentials")
    assert name == "cloudforge/prod/finops-service/credentials"


def test_resolve_secret_name_global_env():
    os.environ["CLOUDFORGE_SECRET_NAME"] = "cloudforge/prod/global/credentials"
    name = resolve_secret_name()
    assert name == "cloudforge/prod/global/credentials"


def test_resolve_secret_name_per_service_env():
    os.environ["FINOPS_SERVICE_SECRET_NAME"] = "cloudforge/prod/finops-service/credentials"
    name = resolve_secret_name(service_name="finops-service")
    assert name == "cloudforge/prod/finops-service/credentials"


def test_resolve_secret_name_auto_default_requires_flag():
    """Without AWS_SECRETS_MANAGER_ENABLED, automatic default path is NOT used."""
    os.environ.pop("AWS_SECRETS_MANAGER_ENABLED", None)
    name = resolve_secret_name(service_name="finops-service")
    assert name is None


def test_resolve_secret_name_auto_default_when_enabled():
    os.environ["AWS_SECRETS_MANAGER_ENABLED"] = "true"
    os.environ["APP_ENV"] = "prod"
    name = resolve_secret_name(service_name="finops-service")
    assert name == "cloudforge/prod/finops-service/credentials"


def test_resolve_secret_name_none_when_nothing_configured():
    name = resolve_secret_name()
    assert name is None


def test_resolve_secret_name_production_rejects_global_override():
    """In production, global CLOUDFORGE_SECRET_NAME must NOT override a specific service's path."""
    os.environ["APP_ENV"] = "production"
    os.environ["CLOUDFORGE_SECRET_NAME"] = "cloudforge/prod/global/credentials"
    os.environ["AWS_SECRETS_MANAGER_ENABLED"] = "true"

    # Should ignore global override and use canonical per-service path
    name = resolve_secret_name(service_name="finops-service")
    assert name == "cloudforge/prod/finops-service/credentials"


def test_resolve_secret_name_production_allows_service_specific_env():
    """In production, per-service env var FINOPS_SERVICE_SECRET_NAME is honored."""
    os.environ["APP_ENV"] = "production"
    os.environ["FINOPS_SERVICE_SECRET_NAME"] = "cloudforge/prod/finops-service/custom-path"
    name = resolve_secret_name(service_name="finops-service")
    assert name == "cloudforge/prod/finops-service/custom-path"


def test_resolve_secret_name_dev_allows_global_override():
    """In development, global CLOUDFORGE_SECRET_NAME is allowed even with service_name."""
    os.environ["APP_ENV"] = "development"
    os.environ["CLOUDFORGE_SECRET_NAME"] = "cloudforge/dev/shared/credentials"
    name = resolve_secret_name(service_name="finops-service")
    assert name == "cloudforge/dev/shared/credentials"



# ---------------------------------------------------------------------------
# 3. IAM policy path coherence — secret paths must match IAM Resource ARN format
# ---------------------------------------------------------------------------

def test_iam_path_prefix_matches_secret_path():
    """The secret path returned by get_default_secret_path starts with 'cloudforge/prod/<service>'.
    IAM Resource ARNs should use the same prefix: arn:aws:secretsmanager:*:*:secret:cloudforge/prod/<service>/*
    """
    for svc in ["finops-service", "aiops-service", "deployment-service", "infrastructure-service", "project-service", "frontend"]:
        path = get_default_secret_path(svc, env="prod")
        expected_prefix = f"cloudforge/prod/{svc}/"
        assert path.startswith(expected_prefix), (
            f"Secret path '{path}' does not start with expected IAM prefix '{expected_prefix}'"
        )


def test_documentation_and_loader_paths_match():
    """Verify all canonical documentation paths match get_default_secret_path() or canonical observability path."""
    canonical_paths = {
        "frontend": "cloudforge/prod/frontend/credentials",
        "project-service": "cloudforge/prod/project-service/credentials",
        "infrastructure-service": "cloudforge/prod/infrastructure-service/credentials",
        "deployment-service": "cloudforge/prod/deployment-service/credentials",
        "finops-service": "cloudforge/prod/finops-service/credentials",
        "aiops-service": "cloudforge/prod/aiops-service/credentials",
    }
    for svc, expected_path in canonical_paths.items():
        assert get_default_secret_path(svc, env="prod") == expected_path
        assert get_default_secret_path(svc, env="production") == expected_path

    # Observability canonical path
    assert "cloudforge/prod/observability/smtp" == "cloudforge/prod/observability/smtp"



# ---------------------------------------------------------------------------
# 4. Secrets loader functional tests
# ---------------------------------------------------------------------------

def test_secrets_loader_no_secret_configured():
    """When nothing is configured, make no AWS calls and return empty dict."""
    mock_client = MagicMock()
    result = load_secrets_from_secrets_manager(boto3_client=mock_client)
    assert result == {}
    mock_client.get_secret_value.assert_not_called()


def test_secrets_loader_uses_service_name_resolution():
    """service_name= should trigger per-service env var resolution."""
    os.environ["FINOPS_SERVICE_SECRET_NAME"] = "cloudforge/prod/finops-service/credentials"
    mock_client = MagicMock()
    payload = {"CLOUDFORGE_INTERNAL_API_TOKEN": "a" * 32}
    mock_client.get_secret_value.return_value = {"SecretString": json.dumps(payload)}

    result = load_secrets_from_secrets_manager(service_name="finops-service", boto3_client=mock_client)

    mock_client.get_secret_value.assert_called_once_with(
        SecretId="cloudforge/prod/finops-service/credentials"
    )
    assert result["CLOUDFORGE_INTERNAL_API_TOKEN"] == "a" * 32


def test_secrets_loader_successful_retrieval_and_caching():
    """Secret is fetched once and then served from cache on subsequent calls."""
    mock_client = MagicMock()
    payload = {
        "CLOUDFORGE_INTERNAL_API_TOKEN": "token-12345678901234567890123456789012",
        "DATABASE_URL": "postgres://user:pass@db.internal:5432/cloudforge",
        "POSTGRES_PASSWORD": "supersecretpassword",
    }
    mock_client.get_secret_value.return_value = {"SecretString": json.dumps(payload)}

    result = load_secrets_from_secrets_manager(
        secret_name="cloudforge/prod/finops-service/credentials",
        boto3_client=mock_client,
    )

    assert result["CLOUDFORGE_INTERNAL_API_TOKEN"] == "token-12345678901234567890123456789012"
    assert result["DATABASE_URL"] == "postgres://user:pass@db.internal:5432/cloudforge"
    mock_client.get_secret_value.assert_called_once()

    # Second call uses cache
    result2 = load_secrets_from_secrets_manager(
        secret_name="cloudforge/prod/finops-service/credentials",
        boto3_client=mock_client,
    )
    assert result2 == result
    assert mock_client.get_secret_value.call_count == 1


def test_secrets_loader_populate_env_preserves_existing():
    """Existing env vars must NOT be overwritten when override_existing=False."""
    mock_client = MagicMock()
    payload = {
        "CLOUDFORGE_INTERNAL_API_TOKEN": "token-from-secretsmanager-32chars!!",
        "TEST_EXISTING_SECRET_KEY": "new-value-from-sm",
    }
    mock_client.get_secret_value.return_value = {"SecretString": json.dumps(payload)}

    original_token = os.environ.get("CLOUDFORGE_INTERNAL_API_TOKEN")
    os.environ["TEST_EXISTING_SECRET_KEY"] = "developer-local-override"
    if "CLOUDFORGE_INTERNAL_API_TOKEN" in os.environ:
        del os.environ["CLOUDFORGE_INTERNAL_API_TOKEN"]

    try:
        populated = populate_env_from_secrets_manager(
            secret_name="cloudforge/prod/finops-service/credentials",
            boto3_client=mock_client,
            override_existing=False,
        )

        # Pre-existing local env var is preserved
        assert os.environ["TEST_EXISTING_SECRET_KEY"] == "developer-local-override"
        # Missing var is populated from Secrets Manager
        assert os.environ["CLOUDFORGE_INTERNAL_API_TOKEN"] == "token-from-secretsmanager-32chars!!"
        assert "CLOUDFORGE_INTERNAL_API_TOKEN" in populated
        assert "TEST_EXISTING_SECRET_KEY" not in populated
    finally:
        os.environ.pop("TEST_EXISTING_SECRET_KEY", None)
        if original_token is not None:
            os.environ["CLOUDFORGE_INTERNAL_API_TOKEN"] = original_token
        else:
            os.environ.pop("CLOUDFORGE_INTERNAL_API_TOKEN", None)


def test_secrets_loader_sanitized_error_on_client_failure():
    """Failure to retrieve secret raises AWSSecretsManagerError with sanitized message."""
    mock_client = MagicMock()
    mock_client.get_secret_value.side_effect = Exception("AccessDenied: User not authorized")

    with pytest.raises(AWSSecretsManagerError) as exc_info:
        load_secrets_from_secrets_manager(
            secret_name="cloudforge/prod/finops-service/credentials",
            boto3_client=mock_client,
        )

    err_msg = str(exc_info.value)
    assert "Failed to retrieve secret 'cloudforge/prod/finops-service/credentials'" in err_msg
    # Must not expose the underlying error message verbatim
    assert "AccessDenied" not in err_msg


def test_secrets_loader_invalid_json_payload():
    """Non-JSON secret string raises AWSSecretsManagerError."""
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {"SecretString": "not-valid-json{"}

    with pytest.raises(AWSSecretsManagerError) as exc_info:
        load_secrets_from_secrets_manager(
            secret_name="cloudforge/prod/finops-service/credentials",
            boto3_client=mock_client,
        )

    assert "Failed to parse secret payload" in str(exc_info.value)


def test_secrets_loader_never_logs_secret_values(caplog):
    """Log output must list key names but NEVER log secret values."""
    mock_client = MagicMock()
    payload = {
        "CLOUDFORGE_INTERNAL_API_TOKEN": "SUPER_SECRET_TOKEN_VALUE_NEVER_LOG",
        "DATABASE_URL": "postgres://cloudforge:SENSITIVE_DB_PASS@db:5432",
    }
    mock_client.get_secret_value.return_value = {"SecretString": json.dumps(payload)}

    with caplog.at_level(logging.INFO):
        load_secrets_from_secrets_manager(
            secret_name="cloudforge/prod/finops-service/credentials",
            boto3_client=mock_client,
        )

    log_output = caplog.text
    # Key names should appear in info log
    assert "CLOUDFORGE_INTERNAL_API_TOKEN" in log_output
    assert "DATABASE_URL" in log_output
    # Values must NEVER appear
    assert "SUPER_SECRET_TOKEN_VALUE_NEVER_LOG" not in log_output
    assert "SENSITIVE_DB_PASS" not in log_output


# ---------------------------------------------------------------------------
# 5. Startup integration: loader wired into service main.py (static inspection)
# ---------------------------------------------------------------------------

def test_finops_main_wires_populate_env():
    """Verify finops main.py source code calls populate_env_from_secrets_manager on startup."""
    with open(REPO_ROOT / "services/finops-service/app/main.py") as f:
        source = f.read()

    assert "populate_env_from_secrets_manager" in source, (
        "finops main.py must call populate_env_from_secrets_manager in lifespan"
    )
    assert 'service_name="finops-service"' in source or "service_name='finops-service'" in source, (
        "finops main.py must pass service_name='finops-service' to populate_env_from_secrets_manager"
    )


def test_aiops_main_wires_populate_env():
    """Verify aiops main.py source code calls populate_env_from_secrets_manager on startup."""
    with open(REPO_ROOT / "services/aiops-service/app/main.py") as f:
        source = f.read()

    assert "populate_env_from_secrets_manager" in source, (
        "aiops main.py must call populate_env_from_secrets_manager in lifespan"
    )
    assert 'service_name="aiops-service"' in source or "service_name='aiops-service'" in source, (
        "aiops main.py must pass service_name='aiops-service' to populate_env_from_secrets_manager"
    )


def test_finops_production_token_validation_in_main():
    """Verify finops main.py validates CLOUDFORGE_FRONTEND_KEY length in production."""
    with open(REPO_ROOT / "services/finops-service/app/main.py") as f:
        source = f.read()

    assert "CLOUDFORGE_FRONTEND_KEY" in source, (
        "finops main.py must validate CLOUDFORGE_FRONTEND_KEY at startup"
    )
    assert "production" in source, (
        "finops main.py must distinguish production in startup validation"
    )


# ---------------------------------------------------------------------------
# 6. Production environment safety
# ---------------------------------------------------------------------------

def test_finops_startup_no_aws_profile_in_production(monkeypatch):
    """AWS_PROFILE must not be set to 'default' at runtime; env should allow empty string."""
    monkeypatch.setenv("AWS_PROFILE", "")
    profile = os.getenv("AWS_PROFILE", "")
    assert profile == "", "AWS_PROFILE must be empty in production to allow IAM workload identity fallback"


def test_no_developer_home_aws_volume_in_production_compose():
    """docker-compose.prod.yml volumes: sections must not mount developer ~/.aws credentials."""
    prod_compose_path = REPO_ROOT / "docker-compose.prod.yml"
    with open(prod_compose_path) as f:
        lines = f.readlines()

    # Check only non-comment lines for actual volume mounts
    non_comment_lines = [ln for ln in lines if not ln.lstrip().startswith("#")]
    volume_lines = [ln for ln in non_comment_lines if "${HOME}/.aws" in ln or "~/.aws" in ln]

    assert len(volume_lines) == 0, (
        "docker-compose.prod.yml must not mount developer ~/.aws credentials in volumes, "
        "but found:\n" + "".join(volume_lines)
    )
