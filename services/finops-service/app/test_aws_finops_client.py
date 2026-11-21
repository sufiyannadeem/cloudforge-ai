from __future__ import annotations

from unittest.mock import MagicMock

from .aws_finops_client import (
    AWSFinOpsClient,
)
from .finops_models import ResourceType


def test_resource_type_mapping():

    assert (
        AWSFinOpsClient._resource_type_from_arn(
            "arn:aws:ec2:eu-west-1:123456789012:"
            "instance/i-123"
        )
        == ResourceType.EC2
    )

    assert (
        AWSFinOpsClient._resource_type_from_arn(
            "arn:aws:rds:eu-west-1:123456789012:"
            "db:test"
        )
        == ResourceType.RDS
    )

    assert (
        AWSFinOpsClient._resource_type_from_arn(
            "arn:aws:ecr:eu-west-1:123456789012:"
            "repository/test"
        )
        == ResourceType.ECR
    )


def test_unknown_resource_type():

    assert (
        AWSFinOpsClient._resource_type_from_arn(
            "arn:aws:unknown:eu-west-1:"
            "123456789012:resource/test"
        )
        == ResourceType.UNKNOWN
    )


def test_service_from_arn():

    assert (
        AWSFinOpsClient._service_from_arn(
            "arn:aws:ec2:eu-west-1:"
            "123456789012:instance/i-123"
        )
        == "ec2"
    )


def test_cost_response_aggregation():

    client = object.__new__(
        AWSFinOpsClient
    )

    mock_ce = MagicMock()

    mock_ce.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon EC2"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "2.50"
                            }
                        },
                    },
                    {
                        "Keys": ["Amazon S3"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "1.25"
                            }
                        },
                    },
                ]
            },
            {
                "Groups": [
                    {
                        "Keys": ["Amazon EC2"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "3.50"
                            }
                        },
                    }
                ]
            },
        ]
    }

    client.cost_explorer = mock_ce

    result = client.get_service_costs(
        start_date="2026-09-20",
        end_date="2026-09-28",
    )

    assert len(result) == 2

    assert result[0].service == (
        "Amazon EC2"
    )

    assert result[0].amount == 6.0

    assert result[1].service == (
        "Amazon S3"
    )

    assert result[1].amount == 1.25


if __name__ == "__main__":

    tests = [
        test_resource_type_mapping,
        test_unknown_resource_type,
        test_service_from_arn,
        test_cost_response_aggregation,
    ]

    for test in tests:
        test()

    print(
        "ALL AWS FINOPS CLIENT TESTS PASSED"
    )
