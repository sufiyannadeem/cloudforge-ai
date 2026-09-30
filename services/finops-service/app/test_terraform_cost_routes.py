import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

FINOPS_SERVICE_DIR = Path(__file__).resolve().parent.parent

if str(FINOPS_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(FINOPS_SERVICE_DIR))

from app.terraform_cost_routes import (  # noqa: E402
    TerraformCostEstimateRequest,
    estimate_terraform_cost,
)


def test_terraform_cost_estimate_create():
    request = TerraformCostEstimateRequest(
        changes=[
            {
                "resource_type": "aws_instance",
                "resource_id": "aws_instance.web",
                "action": "create",
                "region": "eu-west-1",
                "current_quantity": 0,
                "proposed_quantity": 1,
                "pricing": {
                    "unit_monthly_usd": 25.0,
                    "source": "test-pricing",
                    "evidence_available": True,
                    "confidence": "high",
                    "assumptions": ["730 hours/month"],
                },
            }
        ]
    )

    result = estimate_terraform_cost(request)

    assert result.resource_count == 1
    assert result.total_current_monthly_usd == 0
    assert result.total_proposed_monthly_usd == 25.0
    assert result.total_monthly_delta_usd == 25.0
    assert result.evidence_complete is True

    estimate = result.estimates[0]

    assert estimate.resource_id == "aws_instance.web"
    assert estimate.current_monthly_usd == 0
    assert estimate.proposed_monthly_usd == 25.0
    assert estimate.monthly_delta_usd == 25.0
    assert estimate.evidence_available is True
    assert estimate.pricing_source == "test-pricing"


def test_terraform_cost_estimate_missing_pricing_is_explicit():
    request = TerraformCostEstimateRequest(
        changes=[
            {
                "resource_type": "aws_s3_bucket",
                "resource_id": "aws_s3_bucket.assets",
                "action": "create",
                "region": "eu-west-1",
                "current_quantity": 0,
                "proposed_quantity": 1,
            }
        ]
    )

    result = estimate_terraform_cost(request)

    assert result.resource_count == 1
    assert result.total_current_monthly_usd == 0
    assert result.total_proposed_monthly_usd == 0
    assert result.total_monthly_delta_usd == 0
    assert result.evidence_complete is False

    estimate = result.estimates[0]

    assert estimate.evidence_available is False
    assert "required pricing evidence is unavailable" in estimate.calculation
    assert (
        "Zero cost here means unknown cost, not confirmed zero cost."
        in estimate.assumptions
    )


def test_terraform_cost_estimate_rejects_empty_changes():
    with pytest.raises(ValidationError):
        TerraformCostEstimateRequest(changes=[])


def test_terraform_cost_estimate_update():
    request = TerraformCostEstimateRequest(
        changes=[
            {
                "resource_type": "aws_ebs_volume",
                "resource_id": "aws_ebs_volume.data",
                "action": "update",
                "region": "eu-west-1",
                "current_quantity": 100,
                "proposed_quantity": 150,
                "pricing": {
                    "unit_monthly_usd": 0.08,
                    "source": "test-ebs-pricing",
                    "evidence_available": True,
                    "confidence": "high",
                },
            }
        ]
    )

    result = estimate_terraform_cost(request)

    assert result.resource_count == 1
    assert result.total_current_monthly_usd == 8.0
    assert result.total_proposed_monthly_usd == 12.0
    assert result.total_monthly_delta_usd == 4.0


def test_terraform_cost_estimate_delete():
    request = TerraformCostEstimateRequest(
        changes=[
            {
                "resource_type": "aws_instance",
                "resource_id": "aws_instance.web",
                "action": "delete",
                "region": "eu-west-1",
                "current_quantity": 1,
                "proposed_quantity": 0,
                "pricing": {
                    "unit_monthly_usd": 25.0,
                    "source": "test-pricing",
                    "evidence_available": True,
                },
            }
        ]
    )

    result = estimate_terraform_cost(request)

    assert result.total_current_monthly_usd == 25.0
    assert result.total_proposed_monthly_usd == 0
    assert result.total_monthly_delta_usd == -25.0
