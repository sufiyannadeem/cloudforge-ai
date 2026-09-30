from __future__ import annotations

import pytest

from app.terraform_cost_models import TerraformResourceType
from app.terraform_pricing_models import TerraformPricingRateCard
from app.terraform_pricing_service import (
    TerraformPricingConflictError,
    TerraformPricingNotFoundError,
    TerraformPricingService,
)


def pricing(
    *,
    resource_type: TerraformResourceType = TerraformResourceType.AWS_INSTANCE,
    region: str = "eu-west-1",
    unit: str = "instance-month",
    price: float = 25.0,
) -> TerraformPricingRateCard:
    return TerraformPricingRateCard(
        resource_type=resource_type,
        region=region,
        unit=unit,
        unit_monthly_usd=price,
        source="approved-test-evidence",
        evidence_available=True,
        confidence="high",
        assumptions=["Test pricing evidence."],
    )


def test_create_and_get_pricing_evidence() -> None:
    service = TerraformPricingService()

    created = service.create(pricing())

    assert created.resource_type == TerraformResourceType.AWS_INSTANCE
    assert created.region == "eu-west-1"
    assert created.unit == "instance-month"
    assert created.unit_monthly_usd == 25.0
    assert created.evidence_available is True

    fetched = service.get(
        "aws_instance",
        "eu-west-1",
        "instance-month",
    )

    assert fetched == created


def test_duplicate_pricing_identity_is_rejected() -> None:
    service = TerraformPricingService()

    service.create(pricing())

    with pytest.raises(TerraformPricingConflictError):
        service.create(pricing())


def test_identity_is_case_normalized() -> None:
    service = TerraformPricingService()

    service.create(
        pricing(
            region="EU-WEST-1",
            unit="INSTANCE-MONTH",
        )
    )

    with pytest.raises(TerraformPricingConflictError):
        service.create(
            pricing(
                region="eu-west-1",
                unit="instance-month",
            )
        )


def test_different_units_are_distinct_records() -> None:
    service = TerraformPricingService()

    service.create(
        pricing(
            unit="instance-month",
            price=25.0,
        )
    )

    service.create(
        pricing(
            unit="instance-hour",
            price=0.034,
        )
    )

    result = service.list()

    assert result.count == 2


def test_list_filters_by_resource_type() -> None:
    service = TerraformPricingService()

    service.create(pricing())

    service.create(
        pricing(
            resource_type=TerraformResourceType.AWS_EBS_VOLUME,
            unit="gb-month",
            price=10.0,
        )
    )

    result = service.list(resource_type="aws_instance")

    assert result.count == 1
    assert result.records[0].resource_type == (
        TerraformResourceType.AWS_INSTANCE
    )


def test_list_filters_by_region() -> None:
    service = TerraformPricingService()

    service.create(pricing(region="eu-west-1"))

    service.create(
        pricing(
            region="us-east-1",
        )
    )

    result = service.list(region="eu-west-1")

    assert result.count == 1
    assert result.records[0].region == "eu-west-1"


def test_missing_pricing_is_not_found() -> None:
    service = TerraformPricingService()

    with pytest.raises(TerraformPricingNotFoundError):
        service.get(
            "aws_instance",
            "eu-west-1",
            "instance-month",
        )


def test_zero_price_is_valid_but_evidence_can_remain_false() -> None:
    service = TerraformPricingService()

    record = pricing(
        price=0.0,
    ).model_copy(
        update={
            "evidence_available": False,
            "confidence": "unknown",
        }
    )

    created = service.create(record)

    assert created.unit_monthly_usd == 0.0
    assert created.evidence_available is False
    assert created.confidence == "unknown"


def test_invalid_confidence_is_rejected() -> None:
    with pytest.raises(ValueError):
        TerraformPricingRateCard(
            resource_type=TerraformResourceType.AWS_INSTANCE,
            region="eu-west-1",
            unit="instance-month",
            unit_monthly_usd=25.0,
            source="approved-test-evidence",
            evidence_available=True,
            confidence="certain",
        )
