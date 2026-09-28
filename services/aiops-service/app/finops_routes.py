from __future__ import annotations

from fastapi import APIRouter

from .finops_analyzer import FinOpsAnalyzer
from .finops_models import FinOpsReport


router = APIRouter(
    prefix="/api/v1/finops",
    tags=["FinOps"],
)


analyzer = FinOpsAnalyzer()


@router.post(
    "/analyze",
    response_model=FinOpsReport,
)
def analyze_costs(
    payload: dict,
) -> FinOpsReport:

    resources = payload.get(
        "resources",
        [],
    )

    if not isinstance(
        resources,
        list,
    ):
        resources = []

    return analyzer.analyze(
        region=str(
            payload.get(
                "region",
                "eu-west-1",
            )
        ),
        account_id=payload.get(
            "account_id"
        ),
        resources=resources,
    )
