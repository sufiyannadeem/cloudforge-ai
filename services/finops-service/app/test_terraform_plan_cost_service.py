from __future__ import annotations

from .terraform_cost_models import (
    TerraformChangeAction,
    TerraformPricingEvidence,
)
from .terraform_plan_cost_service import TerraformPlanCostService


def _pricing(
    unit_monthly_usd: float,
    *,
    source: str = "test-pricing-evidence",
) -> TerraformPricingEvidence:
    return TerraformPricingEvidence(
        unit_monthly_usd=unit_monthly_usd,
        source=source,
        evidence_available=True,
        confidence="high",
    )


def test_create_plan_is_estimated_from_supplied_pricing() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "region": "eu-west-1",
                        "instance_type": "m7i-flex.large",
                    },
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(
        plan,
        {
            "aws_instance.web": _pricing(40.0),
        },
    )

    estimate = result.cost_report.estimates[0]

    assert estimate.action == TerraformChangeAction.CREATE
    assert estimate.current_monthly_usd == 0
    assert estimate.proposed_monthly_usd == 40
    assert estimate.monthly_delta_usd == 40
    assert estimate.evidence_available is True
    assert result.parse_result.issues == []


def test_update_plan_uses_current_and_proposed_quantities() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_ebs_volume.data",
                "type": "aws_ebs_volume",
                "change": {
                    "actions": ["update"],
                    "before": {
                        "region": "eu-west-1",
                        "size": 100,
                    },
                    "after": {
                        "region": "eu-west-1",
                        "size": 200,
                    },
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(
        plan,
        {
            "aws_ebs_volume.data": _pricing(0.10),
        },
    )

    estimate = result.cost_report.estimates[0]

    assert estimate.action == TerraformChangeAction.UPDATE
    assert estimate.current_monthly_usd == 10
    assert estimate.proposed_monthly_usd == 20
    assert estimate.monthly_delta_usd == 10


def test_delete_plan_has_zero_proposed_cost() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["delete"],
                    "before": {
                        "region": "eu-west-1",
                        "instance_type": "m7i-flex.large",
                    },
                    "after": None,
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(
        plan,
        {
            "aws_instance.web": _pricing(40.0),
        },
    )

    estimate = result.cost_report.estimates[0]

    assert estimate.current_monthly_usd == 40
    assert estimate.proposed_monthly_usd == 0
    assert estimate.monthly_delta_usd == -40


def test_noop_plan_preserves_current_and_proposed_cost() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_nat_gateway.main",
                "type": "aws_nat_gateway",
                "change": {
                    "actions": ["no-op"],
                    "before": {"region": "eu-west-1"},
                    "after": {"region": "eu-west-1"},
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(
        plan,
        {
            "aws_nat_gateway.main": _pricing(32.40),
        },
    )

    estimate = result.cost_report.estimates[0]

    assert estimate.action == TerraformChangeAction.NOOP
    assert estimate.current_monthly_usd == 32.40
    assert estimate.proposed_monthly_usd == 32.40
    assert estimate.monthly_delta_usd == 0


def test_missing_pricing_is_not_invented() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"region": "eu-west-1"},
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(plan)

    estimate = result.cost_report.estimates[0]

    assert estimate.current_monthly_usd == 0
    assert estimate.proposed_monthly_usd == 0
    assert estimate.monthly_delta_usd == 0
    assert estimate.evidence_available is False
    assert "not estimated" in estimate.calculation.lower()


def test_unsupported_resources_are_reported() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_lambda_function.api",
                "type": "aws_lambda_function",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"region": "eu-west-1"},
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(plan)

    assert result.parse_result.unsupported_resources == [
        "aws_lambda_function.api"
    ]
    assert result.cost_report.estimates == []


def test_replacement_is_reported_as_parse_issue() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["delete", "create"],
                    "before": {"region": "eu-west-1"},
                    "after": {"region": "eu-west-1"},
                },
            }
        ]
    }

    result = TerraformPlanCostService().estimate(plan)

    assert result.cost_report.estimates == []
    assert len(result.parse_result.issues) == 1
    assert "replacement" in result.parse_result.issues[0].message.lower()


def test_multiple_resources_produce_aggregate_totals() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"region": "eu-west-1"},
                },
            },
            {
                "address": "aws_s3_bucket.assets",
                "type": "aws_s3_bucket",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"region": "eu-west-1"},
                },
            },
        ]
    }

    result = TerraformPlanCostService().estimate(
        plan,
        {
            "aws_instance.web": _pricing(40.0),
            "aws_s3_bucket.assets": _pricing(12.5),
        },
    )

    assert result.cost_report.resource_count == 2
    assert result.cost_report.total_current_monthly_usd == 0
    assert result.cost_report.total_proposed_monthly_usd == 52.5
    assert result.cost_report.total_monthly_delta_usd == 52.5


def test_parse_issues_do_not_prevent_valid_resources_from_being_estimated() -> None:
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"region": "eu-west-1"},
                },
            },
            {
                "address": "aws_instance.broken",
                "type": "aws_instance",
                "change": {},
            },
        ]
    }

    result = TerraformPlanCostService().estimate(
        plan,
        {
            "aws_instance.web": _pricing(40.0),
        },
    )

    assert len(result.cost_report.estimates) == 1
    assert result.cost_report.estimates[0].resource_id == "aws_instance.web"
    assert len(result.parse_result.issues) == 1
