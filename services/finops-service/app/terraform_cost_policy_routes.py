from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from .access_control import require_finops_access
from .terraform_cost_models import TerraformPricingEvidence
from .terraform_cost_policy_models import (
    TerraformCostPolicy,
    TerraformCostPolicyEvaluation,
)
from .terraform_cost_policy_service import TerraformCostPolicyService
from .terraform_plan_cost_service import TerraformPlanCostService


router = APIRouter(
    prefix="/api/v1/terraform",
    tags=["terraform-cost-policy"],
    dependencies=[Depends(require_finops_access)],
)


_plan_cost_service = TerraformPlanCostService()
_policy_service = TerraformCostPolicyService()


@router.post(
    "/cost-policy-evaluate",
    response_model=TerraformCostPolicyEvaluation,
)
def evaluate_terraform_cost_policy(
    plan: dict[str, Any],
    pricing: dict[str, TerraformPricingEvidence] | None = None,
    policy: TerraformCostPolicy | None = None,
) -> TerraformCostPolicyEvaluation:
    """
    Evaluate a Terraform plan against deterministic cost policy rules.

    Terraform must already have produced the supplied plan JSON.

    This endpoint never executes Terraform, retrieves pricing, or mutates
    infrastructure.
    """

    result = _plan_cost_service.estimate(
        plan,
        pricing=pricing or {},
    )

    return _policy_service.evaluate(
        result,
        policy or TerraformCostPolicy(),
    )
