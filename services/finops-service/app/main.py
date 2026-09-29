from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .aws_finops_routes import router as aws_finops_router
from .finops_optimization_routes import router as finops_optimization_router
from .finops_routes import router as finops_router


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.include_router(finops_router)
app.include_router(aws_finops_router)
app.include_router(finops_optimization_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "service": "finops-service",
        "status": "ok",
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    return {
        "service": "finops-service",
        "status": "ready",
    }
