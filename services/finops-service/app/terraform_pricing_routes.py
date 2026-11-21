from __future__ import annotations

import math
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from .access_control import require_finops_access, require_pricing_admin
from .service_identity import frontend_identity
from .terraform_pricing_models import (
    TerraformPricingRateCard,
    TerraformPricingRateCardListResponse,
    TerraformPricingRateCardResponse,
)
from .terraform_pricing_service import (
    TerraformPricingConflictError,
    TerraformPricingNotFoundError,
    TerraformPricingService,
)


router = APIRouter(
    prefix="/api/v1/terraform/pricing",
    tags=["terraform-pricing"],
    dependencies=[Depends(require_finops_access)],
)


_service = TerraformPricingService()


@router.post(
    "",
    response_model=TerraformPricingRateCardResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_pricing_admin)],
)
def create_pricing_rate_card(
    pricing: TerraformPricingRateCard,
) -> TerraformPricingRateCardResponse:
    try:
        return _service.create(pricing)
    except TerraformPricingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=TerraformPricingRateCardListResponse,
)
def list_pricing_rate_cards(
    resource_type: str | None = Query(default=None),
    region: str | None = Query(default=None),
) -> TerraformPricingRateCardListResponse:
    return _service.list(
        resource_type=resource_type,
        region=region,
    )


@router.get(
    "/{resource_type}/{region}/{unit}",
    response_model=TerraformPricingRateCardResponse,
)
def get_pricing_rate_card(
    resource_type: str,
    region: str,
    unit: str,
) -> TerraformPricingRateCardResponse:
    try:
        return _service.get(
            resource_type=resource_type,
            region=region,
            unit=unit,
        )
    except TerraformPricingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

# This projection exposes configured unit-price evidence only, with no tenant
# usage, account costs, annotations, or access to the administrative catalog.
estimate_router = APIRouter(prefix="/api/v1/terraform/request-estimate")

_INSTANCE = r"[a-z][a-z0-9-]*\.[a-z0-9-]+"
_ESTIMATE_UNITS = {
    "aws_instance": rf"instance-month:{_INSTANCE}",
    "aws_db_instance": rf"instance-month:(?:postgres|mysql|mariadb):db\.{_INSTANCE}:(?:single|multi)-az",
    "aws_eks_node_group": rf"node-month:{_INSTANCE}",
}


@estimate_router.get("/{resource_type}/{region}/{unit}")
def request_unit_estimate(resource_type: str, region: str, unit: str, request: Request) -> dict[str, float]:
    claims = frontend_identity(request, "finops")
    if claims["role"] != "developer":
        require_finops_access(request)
    pattern = _ESTIMATE_UNITS.get(resource_type)
    if (not pattern or len(unit) > 100 or not re.fullmatch(pattern, unit)
            or not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-[0-9]+", region)):
        raise HTTPException(404, "Request estimate unavailable")
    try:
        card = _service.get(resource_type, region, unit)
    except TerraformPricingNotFoundError:
        raise HTTPException(404, "Request estimate unavailable") from None
    if not card.evidence_available or card.confidence not in {"medium", "high"} or not math.isfinite(card.unit_monthly_usd):
        raise HTTPException(404, "Request estimate unavailable")
    return {"unit_monthly_usd": card.unit_monthly_usd}
