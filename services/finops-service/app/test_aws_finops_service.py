from __future__ import annotations

from unittest.mock import MagicMock

from .aws_finops_service import (
    AWSFinOpsService,
)
from .finops_models import (
    AWSFinOpsSnapshot,
    AWSResource,
    AWSServiceCost,
    ResourceType,
)


def test_generate_report_from_snapshot():

    client = MagicMock()

    client.collect_snapshot.return_value = (
        AWSFinOpsSnapshot(
            account_id="123456789012",
            region="eu-west-1",
            cost_start_date="2026-09-20",
            cost_end_date="2026-09-28",
            service_costs=[
                AWSServiceCost(
                    service="Amazon ECR",
                    amount=2.5,
                    start_date="2026-09-20",
                    end_date="2026-09-28",
                )
            ],
            resources=[
                AWSResource(
                    resource_arn=(
                        "arn:aws:ecr:eu-west-1:"
                        "123456789012:"
                        "repository/cloudforge"
                    ),
                    resource_type=ResourceType.ECR,
                    service="ecr",
                    region="eu-west-1",
                    tags={
                        "Environment": "dev",
                        "Owner": "cloudforge",
                    },
                )
            ],
        )
    )

    service = AWSFinOpsService(
        client=client
    )

    report = service.generate_report(
        start_date="2026-09-20",
        end_date="2026-09-28",
    )

    assert report.account_id == (
        "123456789012"
    )

    assert report.region == "eu-west-1"

    assert report.cost_data_source == (
        "aws-cost-explorer"
    )

    assert report.summary.findings_count == 1

    client.collect_snapshot.assert_called_once()


if __name__ == "__main__":

    test_generate_report_from_snapshot()

    print(
        "ALL AWS FINOPS SERVICE TESTS PASSED"
    )
