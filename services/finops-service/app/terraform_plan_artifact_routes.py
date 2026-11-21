from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .access_control import require_finops_access
from .terraform_cost_models import (
    TerraformPricingEvidence,
)
from .terraform_plan_artifact_models import (
    TerraformPlanArtifactCostResponse,
)
from .terraform_plan_artifact_service import (
    TerraformPlanArtifactService,
)


router = APIRouter(
    prefix="/api/v1/terraform",
    tags=["terraform-cost-evidence"],
)


class TerraformPlanArtifactCostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: dict[str, Any]

    source: str = Field(
        min_length=1,
        max_length=200,
    )

    workspace: str = Field(
        min_length=1,
        max_length=200,
    )

    environment: str = Field(
        min_length=1,
        max_length=100,
    )

    region: str = Field(
        min_length=1,
        max_length=100,
    )

    artifact_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    pricing: dict[
        str,
        TerraformPricingEvidence,
    ] = Field(
        default_factory=dict
    )


_service = TerraformPlanArtifactService()


@router.post(
    "/plan-artifact-cost-estimate",
    response_model=TerraformPlanArtifactCostResponse,
)
def estimate_plan_artifact_cost(
    request: TerraformPlanArtifactCostRequest,
    _: str = Depends(require_finops_access),
) -> TerraformPlanArtifactCostResponse:
    try:
        return _service.estimate(
            plan=request.plan,
            source=request.source,
            workspace=request.workspace,
            environment=request.environment,
            region=request.region,
            pricing=request.pricing,
            artifact_id=request.artifact_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
