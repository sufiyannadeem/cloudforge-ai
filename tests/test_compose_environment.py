"""Tests for Docker Compose environment mode selection and production fail-closed boundaries."""
from pathlib import Path
import re
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_local_compose_runs_in_development_mode():
    """Verify local docker-compose.yml defaults all services to development mode."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    with open(compose_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    backend_services = [
        "project-service",
        "infrastructure-service",
        "deployment-service",
        "aiops-service",
        "finops-service",
    ]

    for svc_name in backend_services:
        svc = services.get(svc_name)
        assert svc is not None, f"service {svc_name} missing from docker-compose.yml"
        env = svc.get("environment", {})

        app_env = env.get("APP_ENV")
        assert app_env == "${APP_ENV:-development}", (
            f"{svc_name} in docker-compose.yml must use ${{APP_ENV:-development}}, got: {app_env}"
        )

        # Database URL in local Compose uses local postgres with sslmode=disable
        db_url = env.get("DATABASE_URL", "")
        if db_url:
            assert "sslmode=disable" in db_url or "postgresql://" in db_url, (
                f"{svc_name} database URL should be configured for local development, got {db_url}"
            )
            assert "cloudforge" in db_url

    # Frontend environment
    frontend_env = services.get("frontend", {}).get("environment", {})
    assert frontend_env.get("NEXT_PUBLIC_APP_ENV") == "${APP_ENV:-development}"


def test_production_compose_enforces_production_and_dedicated_principals():
    """Verify docker-compose.prod.yml enforces production and dedicated principals."""
    prod_path = REPO_ROOT / "docker-compose.prod.yml"
    assert prod_path.exists(), "docker-compose.prod.yml must exist"

    with open(prod_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    service_principals = {
        "project-service": "cf_project",
        "infrastructure-service": "cf_infrastructure",
        "deployment-service": "cf_deployment",
        "aiops-service": "cf_aiops",
    }

    for svc_name, principal in service_principals.items():
        svc = services.get(svc_name)
        assert svc is not None, f"{svc_name} missing from docker-compose.prod.yml"
        env = svc.get("environment", {})

        assert env.get("APP_ENV") == "production", f"{svc_name} must have APP_ENV: production in prod compose"
        db_url = env.get("DATABASE_URL", "")
        assert principal in db_url, f"{svc_name} must require dedicated principal {principal} in prod compose"
        assert "verify-full" in db_url, f"{svc_name} must require verify-full in prod compose"
