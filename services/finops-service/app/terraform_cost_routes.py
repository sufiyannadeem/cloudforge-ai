from fastapi import APIRouter
from pydantic import BaseModel, Field

from .terraform_cost_estimator import TerraformCostEstimator
from .terraform_cost_models import (
    TerraformChangeAction,
    TerraformCostEstimateReport,
    TerraformPricingEvidence,
    TerraformResourceChange,
    TerraformResourceType,
)


router = APIRouter(
    prefix="/api/v1/terraform",
    tags=["terraform-cost"],
)


class TerraformPricingEvidenceRequest(BaseModel):
    unit_monthly_usd: float = Field(ge=0)
    source: str = Field(min_length=1)
    evidence_available: bool = False
    confidence: str = "unknown"
    assumptions: list[str] = Field(default_factory=list)


class TerraformResourceChangeRequest(BaseModel):
    resource_type: TerraformResourceType
    resource_id: str = Field(min_length=1)
    action: TerraformChangeAction
    region: str = Field(min_length=1)
    current_quantity: float = Field(default=0, ge=0)
    proposed_quantity: float = Field(default=0, ge=0)
    pricing: TerraformPricingEvidenceRequest | None = None


class TerraformCostEstimateRequest(BaseModel):
    changes: list[TerraformResourceChangeRequest] = Field(min_length=1)


def _pricing(
    evidence: TerraformPricingEvidenceRequest | None,
) -> TerraformPricingEvidence | None:
    if evidence is None:
        return None

    return TerraformPricingEvidence(
        unit_monthly_usd=evidence.unit_monthly_usd,
        source=evidence.source,
        evidence_available=evidence.evidence_available,
        confidence=evidence.confidence,
        assumptions=evidence.assumptions,
    )


def _change(
    request: TerraformResourceChangeRequest,
) -> TerraformResourceChange:
    return TerraformResourceChange(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        action=request.action,
        region=request.region,
        current_quantity=request.current_quantity,
        proposed_quantity=request.proposed_quantity,
        pricing=_pricing(request.pricing),
    )


@router.post(
    "/cost-estimate",
    response_model=TerraformCostEstimateReport,
)
def estimate_terraform_cost(
    request: TerraformCostEstimateRequest,
) -> TerraformCostEstimateReport:
    estimator = TerraformCostEstimator()

    changes = [_change(change) for change in request.changes]

    return estimator.estimate(changes)
