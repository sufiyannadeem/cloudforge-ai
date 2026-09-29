from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .aws_finops_client import AWSFinOpsError
from .aws_finops_service import AWSFinOpsService
from .finops_cost_intelligence import (
    BudgetResponse,
    CostAnomalyResponse,
    CostAttributionResponse,
    CostHistoryResponse,
    CostTrendResponse,
)
from .finops_models import FinOpsReport


router = APIRouter(
    prefix="/api/v1/finops/aws",
    tags=["AWS FinOps"],
)


def _date_range(
    *,
    start_date: str | None,
    end_date: str | None,
    days: int,
) -> tuple[str, str]:
    if start_date and end_date:
        return start_date, end_date

    return AWSFinOpsService.default_cost_intelligence_range(
        days
    )


@router.get(
    "/report",
    response_model=FinOpsReport,
)
def get_aws_finops_report(
    start_date: str | None = Query(
        default=None,
        description="Inclusive YYYY-MM-DD date.",
    ),
    end_date: str | None = Query(
        default=None,
        description="Exclusive YYYY-MM-DD date.",
    ),
) -> FinOpsReport:
    if not start_date or not end_date:
        (
            start_date,
            end_date,
        ) = AWSFinOpsService.default_date_range()

    try:
        service = AWSFinOpsService()

        return service.generate_report(
            start_date=start_date,
            end_date=end_date,
        )

    except AWSFinOpsError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/history",
    response_model=CostHistoryResponse,
)
def get_cost_history(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    days: int = Query(
        default=30,
        ge=1,
        le=365,
    ),
) -> CostHistoryResponse:
    start, end = _date_range(
        start_date=start_date,
        end_date=end_date,
        days=days,
    )

    try:
        return AWSFinOpsService().get_cost_history(
            start_date=start,
            end_date=end,
        )

    except AWSFinOpsError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/trends",
    response_model=CostTrendResponse,
)
def get_cost_trend(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    days: int = Query(
        default=30,
        ge=1,
        le=180,
    ),
) -> CostTrendResponse:
    start, end = _date_range(
        start_date=start_date,
        end_date=end_date,
        days=days,
    )

    try:
        return AWSFinOpsService().get_cost_trend(
            start_date=start,
            end_date=end,
        )

    except AWSFinOpsError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/anomalies",
    response_model=CostAnomalyResponse,
)
def get_cost_anomalies(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    days: int = Query(
        default=30,
        ge=7,
        le=365,
    ),
    threshold: float = Query(
        default=2.5,
        ge=1.0,
        le=10.0,
    ),
) -> CostAnomalyResponse:
    start, end = _date_range(
        start_date=start_date,
        end_date=end_date,
        days=days,
    )

    try:
        return AWSFinOpsService().get_cost_anomalies(
            start_date=start,
            end_date=end,
            threshold=threshold,
        )

    except AWSFinOpsError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/attribution",
    response_model=CostAttributionResponse,
)
def get_cost_attribution(
    dimension: str = Query(
        default="service",
        description=(
            "service, environment, project, "
            "owner, or costcenter"
        ),
    ),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    days: int = Query(
        default=30,
        ge=1,
        le=365,
    ),
) -> CostAttributionResponse:
    start, end = _date_range(
        start_date=start_date,
        end_date=end_date,
        days=days,
    )

    try:
        return AWSFinOpsService().get_cost_attribution(
            start_date=start,
            end_date=end,
            dimension=dimension,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except AWSFinOpsError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/budgets",
    response_model=BudgetResponse,
)
def get_budgets() -> BudgetResponse:
    try:
        return AWSFinOpsService().get_budgets()

    except AWSFinOpsError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
