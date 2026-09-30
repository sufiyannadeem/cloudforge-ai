from __future__ import annotations

import pytest

from app.terraform_cost_estimator import TerraformCostEstimator
from app.terraform_cost_models import (
    TerraformChangeAction,
    TerraformPricingEvidence,
    TerraformResourceChange,
    TerraformResourceType,
)


def pricing(
    amount: float,
    source: str = "test-rate-card",
) -> TerraformPricingEvidence:
    return TerraformPricingEvidence(
        unit_monthly_usd=amount,
        source=source,
        evidence_available=True,
        confidence="high",
        assumptions=["Test pricing evidence."],
    )


def test_create_uses_proposed_quantity_from_zero():
    change = TerraformResourceChange(
        resource_type=TerraformResourceType.AWS_INSTANCE,
        resource_id="web",
        action=TerraformChangeAction.CREATE,
        region="eu-west-1",
        proposed_quantity=2,
        pricing=pricing(42.50),
    )

    result = TerraformCostEstimator().estimate_change(change)

    assert result.current_monthly_usd == 0
    assert result.proposed_monthly_usd == 85
    assert result.monthly_delta_usd == 85
    assert result.evidence_available is True
    assert result.pricing_source == "test-rate-card"


def test_delete_reduces_monthly_cost_to_zero():
    change = TerraformResourceChange(
        resource_type=TerraformResourceType.AWS_INSTANCE,
        resource_id="web",
        action=TerraformChangeAction.DELETE,
        region="eu-west-1",
        current_quantity=2,
        proposed_quantity=0,
        pricing=pricing(42.50),
    )

    result = TerraformCostEstimator().estimate_change(change)

    assert result.current_monthly_usd == 85
    assert result.proposed_monthly_usd == 0
    assert result.monthly_delta_usd == -85


def test_update_calculates_delta():
    change = TerraformResourceChange(
        resource_type=TerraformResourceType.AWS_EBS_VOLUME,
        resource_id="data",
        action=TerraformChangeAction.UPDATE,
        region="eu-west-1",
        current_quantity=100,
        proposed_quantity=150,
        pricing=pricing(0.08),
    )

    result = TerraformCostEstimator().estimate_change(change)

    assert result.current_monthly_usd == 8
    assert result.proposed_monthly_usd == 12
    assert result.monthly_delta_usd == 4


def test_noop_has_zero_delta_when_quantities_match():
    change = TerraformResourceChange(
        resource_type=TerraformResourceType.AWS_NAT_GATEWAY,
        resource_id="nat",
        action=TerraformChangeAction.NOOP,
        region="eu-west-1",
        current_quantity=1,
        proposed_quantity=1,
        pricing=pricing(32.85),
    )

    result = TerraformCostEstimator().estimate_change(change)

    assert result.current_monthly_usd == 32.85
    assert result.proposed_monthly_usd == 32.85
    assert result.monthly_delta_usd == 0


def test_missing_pricing_never_invents_cost():
    change = TerraformResourceChange(
        resource_type=TerraformResourceType.AWS_DB_INSTANCE,
        resource_id="orders-db",
        action=TerraformChangeAction.CREATE,
        region="eu-west-1",
        proposed_quantity=1,
    )

    result = TerraformCostEstimator().estimate_change(change)

    assert result.current_monthly_usd == 0
    assert result.proposed_monthly_usd == 0
    assert result.monthly_delta_usd == 0
    assert result.evidence_available is False
    assert result.pricing_source is None
    assert "not estimated" in result.calculation.lower()
    assert "not confirmed zero" in result.assumptions[1].lower()


def test_pricing_marked_unavailable_is_not_used():
    unavailable = TerraformPricingEvidence(
        unit_monthly_usd=999,
        source="unavailable-rate-card",
        evidence_available=False,
        confidence="unknown",
    )

    change = TerraformResourceChange(
        resource_type=TerraformResourceType.AWS_LB,
        resource_id="public-alb",
        action=TerraformChangeAction.CREATE,
        region="eu-west-1",
        proposed_quantity=1,
        pricing=unavailable,
    )

    result = TerraformCostEstimator().estimate_change(change)

    assert result.evidence_available is False
    assert result.proposed_monthly_usd == 0
    assert result.monthly_delta_usd == 0


def test_report_aggregates_multiple_resources():
    estimator = TerraformCostEstimator()

    changes = [
        TerraformResourceChange(
            resource_type=TerraformResourceType.AWS_INSTANCE,
            resource_id="web",
            action=TerraformChangeAction.CREATE,
            region="eu-west-1",
            proposed_quantity=2,
            pricing=pricing(40),
        ),
        TerraformResourceChange(
            resource_type=TerraformResourceType.AWS_EBS_VOLUME,
            resource_id="data",
            action=TerraformChangeAction.UPDATE,
            region="eu-west-1",
            current_quantity=100,
            proposed_quantity=150,
            pricing=pricing(0.10),
        ),
    ]

    result = estimator.estimate(changes)

    assert result.resource_count == 2
    assert result.total_current_monthly_usd == 10
    assert result.total_proposed_monthly_usd == 95
    assert result.total_monthly_delta_usd == 85
    assert result.evidence_complete is True


def test_report_marks_incomplete_evidence():
    estimator = TerraformCostEstimator()

    changes = [
        TerraformResourceChange(
            resource_type=TerraformResourceType.AWS_INSTANCE,
            resource_id="web",
            action=TerraformChangeAction.CREATE,
            region="eu-west-1",
            proposed_quantity=1,
            pricing=pricing(40),
        ),
        TerraformResourceChange(
            resource_type=TerraformResourceType.AWS_S3_BUCKET,
            resource_id="assets",
            action=TerraformChangeAction.CREATE,
            region="eu-west-1",
            proposed_quantity=1,
        ),
    ]

    result = estimator.estimate(changes)

    assert result.resource_count == 2
    assert result.evidence_complete is False
    assert result.total_monthly_delta_usd == 40


def test_negative_quantity_is_rejected():
    with pytest.raises(ValueError):
        TerraformResourceChange(
            resource_type=TerraformResourceType.AWS_INSTANCE,
            resource_id="bad",
            action=TerraformChangeAction.CREATE,
            region="eu-west-1",
            proposed_quantity=-1,
        )


def test_empty_pricing_source_is_rejected():
    with pytest.raises(ValueError):
        TerraformPricingEvidence(
            unit_monthly_usd=10,
            source="   ",
            evidence_available=True,
        )
