from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from .access_control import require_finops_access
from .terraform_cost_models import (
    TerraformCostEstimateReport,
    TerraformPricingEvidence,
)
from .terraform_plan_cost_service import TerraformPlanCostService


router = APIRouter(
    prefix="/api/v1/terraform",
    tags=["terraform"],
    dependencies=[Depends(require_finops_access)],
)


class TerraformPricingEvidenceRequest(TerraformPricingEvidence):
    model_config = ConfigDict(extra="forbid")


class TerraformPlanCostEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: dict[str, Any]
    pricing: dict[str, TerraformPricingEvidenceRequest] = Field(
        default_factory=dict,
    )


class TerraformPlanCostEstimateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_report: TerraformCostEstimateReport
    parse_issues: list[str] = Field(default_factory=list)
    unsupported_resources: list[str] = Field(default_factory=list)
    parsed_resource_count: int = 0


_service = TerraformPlanCostService()


@router.post(
    "/plan-cost-estimate",
    response_model=TerraformPlanCostEstimateResponse,
)
def estimate_plan_cost(
    request: TerraformPlanCostEstimateRequest,
) -> TerraformPlanCostEstimateResponse:
    pricing = {
        resource_id: evidence.model_copy()
        for resource_id, evidence in request.pricing.items()
    }

    result = _service.estimate(
        request.plan,
        pricing,
    )

    return TerraformPlanCostEstimateResponse(
        cost_report=result.cost_report,
        parse_issues=[
            issue.message
            if issue.resource_address is None
            else f"{issue.resource_address}: {issue.message}"
            for issue in result.parse_result.issues
        ],
        unsupported_resources=result.parse_result.unsupported_resources,
        parsed_resource_count=result.parse_result.resource_count,
    )
