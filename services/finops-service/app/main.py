import logging
import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException

from .service_identity import production_database
from .project_costs import router as project_costs_router
from .project_insights import router as project_insights_router
from .aws_secrets_loader import populate_env_from_secrets_manager
from .aws_finops_routes import router as aws_finops_router
from .finops_anomaly_audit import router as finops_anomaly_audit_router
from .finops_optimization_routes import router as finops_optimization_router
from .finops_routes import router as finops_router
from .terraform_plan_cost_routes import router as terraform_plan_cost_router
from .terraform_cost_routes import router as terraform_cost_router
from .terraform_pricing_routes import estimate_router, router as terraform_pricing_router
from .terraform_cost_policy_routes import router as terraform_cost_policy_router
from .terraform_plan_artifact_routes import (
    router as terraform_plan_artifact_router,
)

logger = logging.getLogger("cloudforge.finops")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Attempt Secrets Manager retrieval at startup if configured
    try:
        populate_env_from_secrets_manager(service_name="finops-service")
    except Exception as exc:
        logger.error("Failed to load secrets during startup: %s", exc)
        if os.getenv("APP_ENV") == "production":
            raise

    # 2. In production, ensure required secrets are present and valid
    if os.getenv("APP_ENV") == "production":
        token = os.getenv("CLOUDFORGE_FRONTEND_KEY", "")
        if len(token) < 32 or "replace-with" in token.lower():
            raise RuntimeError(
                "CLOUDFORGE_FRONTEND_KEY must be configured with at least 32 characters in production"
            )

    for name, principal in [("FINOPS_PROJECT_DATABASE_URL", "cf_finops_project"), ("FINOPS_AUDIT_DATABASE_URL", "cf_finops_audit")]:
        production_database(os.getenv(name, ""), principal)
    yield


app = FastAPI(
    title="CloudForge AI FinOps Service",
    version="1.0.0",
    description=(
        "Read-only cloud cost intelligence, Kubernetes workload "
        "cost analysis, budgets, anomalies, attribution, and "
        "human-approved optimization recommendations."
    ),
    lifespan=lifespan,
)

app.include_router(project_costs_router)
app.include_router(project_insights_router)
app.include_router(finops_router)
app.include_router(aws_finops_router)
app.include_router(finops_anomaly_audit_router)
app.include_router(finops_optimization_router)
app.include_router(terraform_plan_cost_router)
app.include_router(terraform_cost_router)
app.include_router(terraform_pricing_router)
app.include_router(estimate_router)
app.include_router(terraform_cost_policy_router)
app.include_router(terraform_plan_artifact_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "service": "finops-service",
        "status": "ok",
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    # Connectivity is bounded and failure details never leave the health endpoint.
    for name in ['FINOPS_PROJECT_DATABASE_URL', 'FINOPS_AUDIT_DATABASE_URL']:
        dsn = os.getenv(name)
        if not dsn:
            if os.getenv("APP_ENV") == "production":
                raise HTTPException(status_code=503, detail="Database readiness unavailable")
            continue
        try:
            production_database(dsn, "cf_finops_project" if name == "FINOPS_PROJECT_DATABASE_URL" else "cf_finops_audit")
            with psycopg.connect(dsn, connect_timeout=2, autocommit=True,
                                 options="-c statement_timeout=1000") as db:
                db.execute("SELECT 1")
        except (psycopg.Error, RuntimeError):
            raise HTTPException(status_code=503, detail="Database readiness unavailable") from None
    return {
        "service": "finops-service",
        "status": "ready",
    }
