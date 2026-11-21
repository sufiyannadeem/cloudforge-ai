"""
AWS Secrets Manager loader for CloudForge AI services.

Loads sensitive runtime configuration (internal tokens, database credentials,
session secrets) from AWS Secrets Manager using standard IAM workload identity
(IRSA, EKS Pod Identity, or EC2 Instance Profiles).

Per-service secret naming convention:
- cloudforge/<env>/aiops-service/credentials
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("cloudforge.secrets")

_CACHED_SECRETS: dict[str, str] = {}
_CACHED_SECRET_NAME: str | None = None
_SECRETS_LOADED = False


class AWSSecretsManagerError(RuntimeError):
    """Raised when an AWS Secrets Manager operation fails."""


def reset_secrets_cache() -> None:
    """Reset the internal secret cache (primarily for automated tests)."""
    global _SECRETS_LOADED, _CACHED_SECRET_NAME
    _CACHED_SECRETS.clear()
    _CACHED_SECRET_NAME = None
    _SECRETS_LOADED = False


def get_default_secret_path(service_name: str, env: str = "prod") -> str:
    """Return the canonical per-service Secrets Manager path."""
    clean_svc = service_name.strip().lower()
    clean_env = env.strip().lower()
    if clean_env == "production":
        clean_env = "prod"
    elif clean_env == "development":
        clean_env = "dev"
    return f"cloudforge/{clean_env}/{clean_svc}/credentials"



def resolve_secret_name(
    secret_name: str | None = None,
    service_name: str | None = None,
) -> str | None:
    """Resolve the secret name from parameters, environment variables, or per-service defaults.

    Resolution priority:
    1. Explicit ``secret_name`` argument (always honoured — caller takes responsibility).
    2. Per-service environment variable (e.g. ``AIOPS_SERVICE_SECRET_NAME``).
    3. Global override env var (``CLOUDFORGE_SECRET_NAME`` / ``AWS_SECRETS_MANAGER_SECRET_NAME``).
       Blocked in production when ``service_name`` is supplied to prevent cross-service secret
       access — an aiops container must not be able to load finops credentials by mistake.
    4. Automatic canonical default when ``AWS_SECRETS_MANAGER_ENABLED=true`` and ``service_name``
       is supplied.

    Returns ``None`` when no secret is configured (opt-in; falls back to env-var injection).
    """
    # 1. Explicit argument always wins
    if secret_name and secret_name.strip():
        return secret_name.strip()

    app_env = os.getenv("APP_ENV", "").strip().lower()
    is_production = app_env == "production"

    # 2. Per-service environment variable is always safe (scoped to this service)
    if service_name:
        svc_env_var = f"{service_name.upper().replace('-', '_')}_SECRET_NAME"
        svc_secret = os.getenv(svc_env_var)
        if svc_secret and svc_secret.strip():
            return svc_secret.strip()

    # 3. Global override — allowed only in non-production or when no service_name is known.
    #    In production with a known service_name, the global override is rejected: it could
    #    name any secret in the account and violates per-service isolation.
    global_secret = os.getenv("CLOUDFORGE_SECRET_NAME") or os.getenv("AWS_SECRETS_MANAGER_SECRET_NAME")
    if global_secret and global_secret.strip():
        if is_production and service_name:
            logger.warning(
                "CLOUDFORGE_SECRET_NAME global override is not permitted in production when "
                "service_name='%s' is set. Use %s_SECRET_NAME instead to enforce per-service "
                "secret isolation. Ignoring global override.",
                service_name,
                service_name.upper().replace("-", "_"),
            )
            # Fall through to automatic default below
        else:
            return global_secret.strip()

    # 4. Automatic default path when Secrets Manager is explicitly enabled
    sm_enabled = os.getenv("AWS_SECRETS_MANAGER_ENABLED", "").lower() in ("true", "1", "yes")
    if sm_enabled and service_name:
        env = os.getenv("APP_ENV", "prod")
        return get_default_secret_path(service_name, env=env)

    return None



def load_secrets_from_secrets_manager(
    secret_name: str | None = None,
    service_name: str | None = None,
    region_name: str | None = None,
    boto3_client: Any = None,
) -> dict[str, str]:
    """
    Retrieve and parse a JSON secret payload from AWS Secrets Manager.

    Uses standard AWS IAM workload identity (IRSA, EKS Pod Identity, or EC2 Instance Profile).
    Never logs or leaks secret values.
    """
    global _SECRETS_LOADED, _CACHED_SECRET_NAME

    target_secret = resolve_secret_name(secret_name=secret_name, service_name=service_name)
    if not target_secret:
        return {}

    if _SECRETS_LOADED and _CACHED_SECRET_NAME == target_secret:
        return dict(_CACHED_SECRETS)

    region = region_name or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "eu-west-1")

    client = boto3_client
    if client is None:
        try:
            import boto3

            client = boto3.client("secretsmanager", region_name=region)
        except Exception as exc:
            raise AWSSecretsManagerError(
                f"Unable to initialize AWS Secrets Manager client in region '{region}': {type(exc).__name__}"
            ) from exc

    try:
        response = client.get_secret_value(SecretId=target_secret)
    except Exception as exc:
        exc_type = type(exc).__name__
        logger.error(
            "Failed to retrieve secret from AWS Secrets Manager",
            extra={"secret_name": target_secret, "error_type": exc_type},
        )
        raise AWSSecretsManagerError(
            f"Failed to retrieve secret '{target_secret}' from AWS Secrets Manager ({exc_type})"
        ) from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        return {}

    try:
        parsed = json.loads(secret_string)
        if not isinstance(parsed, dict):
            raise ValueError("SecretString must be a JSON object mapping")
    except Exception as exc:
        raise AWSSecretsManagerError(
            f"Failed to parse secret payload from '{target_secret}' as JSON: {type(exc).__name__}"
        ) from exc

    for k, v in parsed.items():
        if isinstance(v, str):
            _CACHED_SECRETS[k] = v
        elif v is not None:
            _CACHED_SECRETS[k] = str(v)

    _SECRETS_LOADED = True
    _CACHED_SECRET_NAME = target_secret
    logger.info(
        "Successfully loaded %d secret keys from AWS Secrets Manager [%s]: %s",
        len(_CACHED_SECRETS),
        target_secret,
        sorted(_CACHED_SECRETS.keys()),
    )

    return dict(_CACHED_SECRETS)


def populate_env_from_secrets_manager(
    secret_name: str | None = None,
    service_name: str | None = None,
    region_name: str | None = None,
    boto3_client: Any = None,
    override_existing: bool = False,
) -> list[str]:
    """
    Load secrets from Secrets Manager and inject them into os.environ.

    Returns the list of environment variable names that were populated.
    Does NOT overwrite existing environment variables unless override_existing=True.
    """
    secrets = load_secrets_from_secrets_manager(
        secret_name=secret_name,
        service_name=service_name,
        region_name=region_name,
        boto3_client=boto3_client,
    )

    populated_keys: list[str] = []
    for key, value in secrets.items():
        if override_existing or key not in os.environ or not os.environ[key]:
            os.environ[key] = value
            populated_keys.append(key)

    return populated_keys
