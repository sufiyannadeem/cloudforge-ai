from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .slo_models import SLODefinition, SLOSummary
from .slo_service import slo_service


router = APIRouter(
    prefix="/api/v1/slo",
    tags=["SLO"],
)


@router.get(
    "/definitions",
    response_model=list[SLODefinition],
)
def get_slo_definitions(
    service: str = Query(
        default="deployment-service",
        min_length=1,
    ),
) -> list[SLODefinition]:
    return slo_service.definitions(service)


@router.get(
    "/summary",
    response_model=SLOSummary,
)
def get_slo_summary(
    service: str = Query(
        default="deployment-service",
        min_length=1,
    ),
) -> SLOSummary:
    try:
        return slo_service.evaluate(service)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to evaluate SLOs: {error}",
        ) from error
