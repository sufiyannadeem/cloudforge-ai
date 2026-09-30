from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .access_control import require_finops_access
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
