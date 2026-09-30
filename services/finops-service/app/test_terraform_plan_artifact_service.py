from __future__ import annotations

import hashlib

import pytest

from app.terraform_cost_models import TerraformPricingEvidence
from app.terraform_plan_artifact_service import (
    TerraformPlanArtifactService,
)


def create_plan() -> dict:
    return {
        "format_version": "1.0",
        "resource_changes": [
            {
                "address": "aws_instance.demo",
                "mode": "managed",
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
        ],
    }


def create_pricing() -> dict[str, TerraformPricingEvidence]:
    return {
        "aws_instance.demo": TerraformPricingEvidence(
            unit_monthly_usd=25.0,
            source="approved-pricing-evidence",
            evidence_available=True,
            confidence="high",
            assumptions=[
                "Monthly unit price supplied externally"
            ],
        )
    }


def test_create_artifact_generates_metadata() -> None:
    service = TerraformPlanArtifactService()

    artifact = service.create_artifact(
        plan=create_plan(),
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
    )

    assert artifact.artifact_id
    assert artifact.source == "github-actions"
    assert artifact.workspace == "cloudforge"
    assert artifact.environment == "production"
    assert artifact.region == "eu-west-1"
    assert artifact.resource_count == 1
    assert len(artifact.plan_hash) == 64


def test_same_plan_produces_same_hash() -> None:
    service = TerraformPlanArtifactService()
    plan = create_plan()

    first = service.create_artifact(
        plan=plan,
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
    )

    second = service.create_artifact(
        plan=plan,
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
    )

    assert first.plan_hash == second.plan_hash


def test_hash_matches_sha256_canonical_json() -> None:
    service = TerraformPlanArtifactService()
    plan = create_plan()

    artifact = service.create_artifact(
        plan=plan,
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
    )

    import json

    canonical = json.dumps(
        plan,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    expected = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    assert artifact.plan_hash == expected


def test_different_plan_produces_different_hash() -> None:
    service = TerraformPlanArtifactService()

    first_plan = create_plan()
    second_plan = create_plan()

    second_plan["resource_changes"][0]["address"] = (
        "aws_instance.other"
    )

    first = service.create_artifact(
        plan=first_plan,
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
    )

    second = service.create_artifact(
        plan=second_plan,
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
    )

    assert first.plan_hash != second.plan_hash


def test_estimate_with_complete_pricing_has_full_coverage() -> None:
    service = TerraformPlanArtifactService()

    result = service.estimate(
        plan=create_plan(),
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
        pricing=create_pricing(),
    )

    assert result.parsed_resource_count == 1
    assert result.evidence_coverage.parsed_resource_count == 1
    assert result.evidence_coverage.priced_resource_count == 1
    assert result.evidence_coverage.missing_pricing_resource_count == 0
    assert result.evidence_coverage.coverage_percent == 100.0
    assert result.evidence_coverage.complete is True


def test_estimate_without_pricing_reports_zero_coverage() -> None:
    service = TerraformPlanArtifactService()

    result = service.estimate(
        plan=create_plan(),
        source="github-actions",
        workspace="cloudforge",
        environment="production",
        region="eu-west-1",
    )

    assert result.parsed_resource_count == 1
    assert result.evidence_coverage.priced_resource_count == 0
    assert result.evidence_coverage.missing_pricing_resource_count == 1
    assert result.evidence_coverage.coverage_percent == 0.0
    assert result.evidence_coverage.complete is False


@pytest.mark.parametrize(
    "plan",
    [
        {},
        {"resource_changes": None},
        {"resource_changes": {}},
        {"resource_changes": [None]},
        {"resource_changes": [{}]},
        {
            "resource_changes": [
                {
                    "type": "aws_instance",
                    "change": {
                        "actions": ["create"],
                    },
                }
            ]
        },
        {
            "resource_changes": [
                {
                    "address": "aws_instance.demo",
                    "change": {
                        "actions": ["create"],
                    },
                }
            ]
        },
        {
            "resource_changes": [
                {
                    "address": "aws_instance.demo",
                    "type": "aws_instance",
                }
            ]
        },
    ],
)
def test_invalid_plan_structure_is_rejected(
    plan: dict,
) -> None:
    service = TerraformPlanArtifactService()

    with pytest.raises(ValueError):
        service.create_artifact(
            plan=plan,
            source="github-actions",
            workspace="cloudforge",
            environment="production",
            region="eu-west-1",
        )
