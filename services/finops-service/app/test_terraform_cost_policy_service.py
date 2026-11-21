from __future__ import annotations

from .terraform_cost_models import TerraformPricingEvidence
from .terraform_cost_policy_models import (
    TerraformCostPolicy,
    TerraformCostPolicyDecision,
)
from .terraform_cost_policy_service import TerraformCostPolicyService
from .terraform_plan_cost_service import TerraformPlanCostService


def _pricing(unit_monthly_usd: float) -> TerraformPricingEvidence:
    return TerraformPricingEvidence(
        unit_monthly_usd=unit_monthly_usd,
        source="test-pricing-evidence",
        evidence_available=True,
        confidence="high",
    )


def _create_plan(address: str = "aws_instance.web") -> dict:
    return {
        "resource_changes": [
            {
                "address": address,
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "region": "eu-west-1",
                    },
                },
            }
        ]
    }


def _estimate(
    price: float,
    *,
    include_pricing: bool = True,
):
    pricing = (
        {"aws_instance.web": _pricing(price)}
        if include_pricing
        else {}
    )

    return TerraformPlanCostService().estimate(
        _create_plan(),
        pricing=pricing,
    )


def test_cost_increase_within_threshold_is_allowed() -> None:
    result = _estimate(25.0)

    evaluation = TerraformCostPolicyService.evaluate(
        result,
        TerraformCostPolicy(
            max_monthly_increase_usd=100.0,
            max_monthly_increase_percent=20.0,
        ),
    )

    assert evaluation.decision == TerraformCostPolicyDecision.ALLOW
    assert evaluation.comparison.proposed_monthly_usd == 25.0
    assert evaluation.comparison.monthly_delta_usd == 25.0


def test_cost_increase_above_usd_threshold_is_blocked() -> None:
    result = _estimate(150.0)

    evaluation = TerraformCostPolicyService.evaluate(
        result,
        TerraformCostPolicy(
            max_monthly_increase_usd=100.0,
            max_monthly_increase_percent=200.0,
        ),
    )

    assert evaluation.decision == TerraformCostPolicyDecision.BLOCK


def test_percentage_threshold_requires_review() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["update"],
                    "before": {
                        "region": "eu-west-1",
                    },
                    "after": {
                        "region": "eu-west-1",
                    },
                },
            },
            {
                "address": "aws_instance.new",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "region": "eu-west-1",
                    },
                },
            },
        ]
    }

    pricing = {
        "aws_instance.web": _pricing(100.0),
        "aws_instance.new": _pricing(30.0),
    }

    result = TerraformPlanCostService().estimate(
        plan,
        pricing=pricing,
    )

    evaluation = TerraformCostPolicyService.evaluate(
        result,
        TerraformCostPolicy(
            max_monthly_increase_usd=100.0,
            max_monthly_increase_percent=20.0,
        ),
    )

    assert evaluation.decision == TerraformCostPolicyDecision.REVIEW


def test_incomplete_evidence_blocks_by_default() -> None:
    result = _estimate(
        25.0,
        include_pricing=False,
    )

    evaluation = TerraformCostPolicyService.evaluate(
        result,
        TerraformCostPolicy(),
    )

    assert evaluation.decision == TerraformCostPolicyDecision.BLOCK
    assert evaluation.comparison.evidence_complete is False


def test_incomplete_evidence_can_require_review() -> None:
    result = _estimate(
        25.0,
        include_pricing=False,
    )

    evaluation = TerraformCostPolicyService.evaluate(
        result,
        TerraformCostPolicy(
            block_if_evidence_incomplete=False,
            review_if_evidence_incomplete=True,
        ),
    )

    assert evaluation.decision == TerraformCostPolicyDecision.REVIEW


def test_incomplete_evidence_can_be_allowed() -> None:
    result = _estimate(
        25.0,
        include_pricing=False,
    )

    evaluation = TerraformCostPolicyService.evaluate(
        result,
        TerraformCostPolicy(
            block_if_evidence_incomplete=False,
            review_if_evidence_incomplete=False,
        ),
    )

    assert evaluation.decision == TerraformCostPolicyDecision.ALLOW


def test_no_cost_increase_is_allowed() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["no-op"],
                    "before": {
                        "region": "eu-west-1",
                    },
                    "after": {
                        "region": "eu-west-1",
                    },
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(
        plan,
        pricing={
            "aws_instance.web": _pricing(25.0),
        },
    )

    evaluation = TerraformCostPolicyService.evaluate(
        result,
        TerraformCostPolicy(),
    )

    assert evaluation.decision == TerraformCostPolicyDecision.ALLOW
    assert evaluation.comparison.monthly_delta_usd == 0.0
    assert evaluation.comparison.monthly_delta_percent == 0.0


def test_create_from_zero_has_no_percentage_denominator() -> None:
    result = _estimate(25.0)

    comparison = TerraformCostPolicyService.compare(result)

    assert comparison.current_monthly_usd == 0.0
    assert comparison.proposed_monthly_usd == 25.0
    assert comparison.monthly_delta_percent is None
