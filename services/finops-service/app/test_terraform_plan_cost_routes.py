from __future__ import annotations

from .terraform_plan_cost_routes import (
    TerraformPlanCostEstimateRequest,
    TerraformPricingEvidenceRequest,
    estimate_plan_cost,
)


def test_plan_cost_route_returns_combined_result() -> None:
    request = TerraformPlanCostEstimateRequest(
        plan={
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
        },
        pricing={
            "aws_instance.web": TerraformPricingEvidenceRequest(
                unit_monthly_usd=40.0,
                source="approved-test-evidence",
                evidence_available=True,
                confidence="high",
            ),
        },
    )

    response = estimate_plan_cost(request)

    assert response.parsed_resource_count == 1
    assert response.parse_issues == []
    assert response.unsupported_resources == []
    assert response.cost_report.total_proposed_monthly_usd == 40.0


def test_plan_cost_route_reports_unsupported_resources() -> None:
    request = TerraformPlanCostEstimateRequest(
        plan={
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
    )

    response = estimate_plan_cost(request)

    assert response.parsed_resource_count == 1
    assert response.unsupported_resources == [
        "aws_lambda_function.api"
    ]
    assert response.cost_report.estimates == []


def test_plan_cost_route_reports_parse_issues() -> None:
    request = TerraformPlanCostEstimateRequest(
        plan={
            "resource_changes": [
                {
                    "address": "aws_instance.broken",
                    "type": "aws_instance",
                    "change": {
                        "actions": ["delete", "create"],
                        "before": {"region": "eu-west-1"},
                        "after": {"region": "eu-west-1"},
                    },
                }
            ]
        }
    )

    response = estimate_plan_cost(request)

    assert response.cost_report.estimates == []
    assert len(response.parse_issues) == 1
    assert "replacement" in response.parse_issues[0].lower()
