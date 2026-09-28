from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .aws_finops_client import AWSFinOpsError
from .aws_finops_service import AWSFinOpsService
from .finops_models import FinOpsReport


router = APIRouter(
    prefix="/api/v1/finops/aws",
    tags=["AWS FinOps"],
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
