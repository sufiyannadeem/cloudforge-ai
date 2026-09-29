from __future__ import annotations

from .finops_analyzer import FinOpsAnalyzer
from .finops_models import (
    CostSeverity,
    ResourceType,
)


def test_idle_expensive_resource():

    analyzer = FinOpsAnalyzer()

    report = analyzer.analyze(
        region="eu-west-1",
        account_id="test-account",
        resources=[
            {
                "resource_id": "nat-123",
                "resource_type": "nat_gateway",
                "service": "NAT Gateway",
                "estimated_monthly_cost": 120.0,
                "idle": True,
                "tags": {},
            }
        ],
    )

    assert report.summary.findings_count == 1

    finding = report.findings[0]

    assert finding.resource_type == (
        ResourceType.NAT_GATEWAY
    )

    assert finding.idle is True

    assert finding.untagged is True

    assert finding.severity == (
        CostSeverity.CRITICAL
    )

    assert (
        report.summary.idle_monthly_cost
        == 120.0
    )


def test_untagged_resource():

    analyzer = FinOpsAnalyzer()

    report = analyzer.analyze(
        region="eu-west-1",
        resources=[
            {
                "resource_id": "ecr-123",
                "resource_type": "ecr",
                "service": "Amazon ECR",
                "estimated_monthly_cost": 5.0,
                "idle": False,
                "tags": {},
            }
        ],
    )

    finding = report.findings[0]

    assert finding.untagged is True

    assert finding.severity == (
        CostSeverity.INFO
    )

    assert (
        report.summary.untagged_resource_count
        == 1
    )


def test_normal_resource():

    analyzer = FinOpsAnalyzer()

    report = analyzer.analyze(
        region="eu-west-1",
        resources=[
            {
                "resource_id": "ecr-456",
                "resource_type": "ecr",
                "service": "Amazon ECR",
                "estimated_monthly_cost": 4.0,
                "idle": False,
                "tags": {
                    "Environment": "dev",
                    "Owner": "cloudforge",
                },
            }
        ],
    )

    finding = report.findings[0]

    assert finding.idle is False

    assert finding.untagged is False

    assert finding.severity == (
        CostSeverity.INFO
    )


def test_unknown_resource_type_is_safe():

    analyzer = FinOpsAnalyzer()

    report = analyzer.analyze(
        region="eu-west-1",
        resources=[
            {
                "resource_id": "unknown-123",
                "resource_type": "future-aws-service",
                "service": "Future AWS Service",
                "estimated_monthly_cost": 10.0,
                "idle": False,
                "tags": {},
            }
        ],
    )

    finding = report.findings[0]

    assert finding.resource_type == (
        ResourceType.UNKNOWN
    )


def test_multiple_resources_summary():

    analyzer = FinOpsAnalyzer()

    report = analyzer.analyze(
        region="eu-west-1",
        resources=[
            {
                "resource_id": "ec2-1",
                "resource_type": "ec2",
                "service": "EC2",
                "estimated_monthly_cost": 20.0,
                "idle": False,
                "tags": {
                    "Environment": "dev",
                },
            },
            {
                "resource_id": "rds-1",
                "resource_type": "rds",
                "service": "RDS",
                "estimated_monthly_cost": 80.0,
                "idle": True,
                "tags": {},
            },
        ],
    )

    assert report.summary.findings_count == 2

    assert (
        report.summary.total_estimated_monthly_cost
        == 100.0
    )

    assert (
        report.summary.idle_monthly_cost
        == 80.0
    )

    assert (
        report.summary.untagged_resource_count
        == 1
    )


if __name__ == "__main__":

    tests = [
        test_idle_expensive_resource,
        test_untagged_resource,
        test_normal_resource,
        test_unknown_resource_type_is_safe,
        test_multiple_resources_summary,
    ]

    for test in tests:
        test()

    print(
        "ALL FINOPS ANALYZER TESTS PASSED"
    )
