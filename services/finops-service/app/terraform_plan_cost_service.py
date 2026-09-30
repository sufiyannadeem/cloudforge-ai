from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .terraform_cost_estimator import TerraformCostEstimator
from .terraform_cost_models import (
    TerraformCostEstimateReport,
    TerraformPricingEvidence,
    TerraformResourceChange,
)
from .terraform_plan_parser import TerraformPlanParseResult, TerraformPlanParser


class TerraformPlanCostResult:
    """
    Combined Terraform plan parsing and deterministic cost estimation result.

    This service:
    - does not execute Terraform;
    - does not call AWS;
    - does not query pricing APIs;
    - does not infer pricing;
    - does not mutate infrastructure.

    Pricing evidence is supplied explicitly by the caller.
    """

    def __init__(
        self,
        *,
        parse_result: TerraformPlanParseResult,
        cost_report: TerraformCostEstimateReport,
    ) -> None:
        self.parse_result = parse_result
        self.cost_report = cost_report


class TerraformPlanCostService:
    def __init__(
        self,
        *,
        parser: TerraformPlanParser | None = None,
        estimator: TerraformCostEstimator | None = None,
    ) -> None:
        self.parser = parser or TerraformPlanParser()
        self.estimator = estimator or TerraformCostEstimator()

    def estimate(
        self,
        plan: Mapping[str, Any],
        pricing: Mapping[str, TerraformPricingEvidence] | None = None,
    ) -> TerraformPlanCostResult:
        parse_result = self.parser.parse(plan)

        pricing = pricing or {}

        changes = [
            self._with_pricing(change, pricing)
            for change in parse_result.changes
        ]

        cost_report = self.estimator.estimate(changes)

        return TerraformPlanCostResult(
            parse_result=parse_result,
            cost_report=cost_report,
        )

    @staticmethod
    def _with_pricing(
        change: TerraformResourceChange,
        pricing: Mapping[str, TerraformPricingEvidence],
    ) -> TerraformResourceChange:
        evidence = pricing.get(change.resource_id)

        if evidence is None:
            return change

        return change.model_copy(update={"pricing": evidence})
