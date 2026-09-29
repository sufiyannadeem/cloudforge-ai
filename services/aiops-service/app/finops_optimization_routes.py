from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .finops_optimization_models import (
    AWSOptimizationObservation,
    OptimizationReport,
)
from .finops_optimization_service import (
    FinOpsOptimizationService,
)


router = APIRouter(
    prefix="/api/v1/finops/optimization",
    tags=["FinOps Optimization"],
)


service = FinOpsOptimizationService()


@router.get(
    "/kubernetes",
    response_model=OptimizationReport,
)
def analyze_kubernetes_optimization() -> OptimizationReport:
    try:
        return service.analyze_kubernetes()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Kubernetes optimization failed: {exc}",
        ) from exc


@router.post(
    "/aws",
    response_model=OptimizationReport,
)
def analyze_aws_optimization(
    observation: AWSOptimizationObservation,
) -> OptimizationReport:
    try:
        return service.analyze_aws(
            observation
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"AWS optimization failed: {exc}",
        ) from exc


@router.post(
    "/all",
    response_model=OptimizationReport,
)
def analyze_all_optimization(
    observation: AWSOptimizationObservation | None = None,
) -> OptimizationReport:
    try:
        return service.analyze_all(
            observation
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"FinOps optimization failed: {exc}",
        ) from exc
