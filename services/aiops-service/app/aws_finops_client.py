from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
)

from .finops_models import (
    AWSFinOpsSnapshot,
    AWSResource,
    AWSServiceCost,
    ResourceType,
)


RESOURCE_TYPE_MAP = {
    "ec2:instance": ResourceType.EC2,
    "rds:db": ResourceType.RDS,
    "ecr:repository": ResourceType.ECR,
    "s3:bucket": ResourceType.S3,
    "elasticloadbalancing:loadbalancer":
        ResourceType.LOAD_BALANCER,
    "eks:cluster": ResourceType.EKS,
}


class AWSFinOpsError(RuntimeError):
    """Raised when a read-only AWS FinOps operation fails."""


class AWSFinOpsClient:
    """
    Read-only AWS FinOps adapter.

    This class:
      - reads AWS account identity
      - reads Cost Explorer data
      - reads tagged resource inventory

    It never:
      - creates resources
      - deletes resources
      - modifies resources
      - changes tags
      - changes Terraform
      - changes Kubernetes
    """

    def __init__(
        self,
        *,
        region: str = "eu-west-1",
    ) -> None:

        self.region = region

        self.sts = boto3.client(
            "sts",
            region_name=region,
        )

        # Cost Explorer API uses the us-east-1 endpoint.
        self.cost_explorer = boto3.client(
            "ce",
            region_name="us-east-1",
        )

        self.tagging = boto3.client(
            "resourcegroupstaggingapi",
            region_name=region,
        )

    def get_account_id(self) -> str:

        try:
            response = (
                self.sts.get_caller_identity()
            )

            account_id = response.get(
                "Account"
            )

            if not account_id:
                raise AWSFinOpsError(
                    "AWS identity response did not "
                    "contain an account ID."
                )

            return str(account_id)

        except (
            ClientError,
            BotoCoreError,
        ) as exc:
            raise AWSFinOpsError(
                f"Unable to determine AWS account: {exc}"
            ) from exc

    def get_service_costs(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> list[AWSServiceCost]:

        try:
            response = (
                self.cost_explorer
                .get_cost_and_usage(
                    TimePeriod={
                        "Start": start_date,
                        "End": end_date,
                    },
                    Granularity="DAILY",
                    Metrics=[
                        "UnblendedCost"
                    ],
                    GroupBy=[
                        {
                            "Type": "DIMENSION",
                            "Key": "SERVICE",
                        }
                    ],
                )
            )

        except (
            ClientError,
            BotoCoreError,
        ) as exc:
            raise AWSFinOpsError(
                f"Unable to query AWS Cost Explorer: {exc}"
            ) from exc

        totals: dict[str, float] = {}

        for result in response.get(
            "ResultsByTime",
            [],
        ):
            for group in result.get(
                "Groups",
                [],
            ):
                keys = group.get(
                    "Keys",
                    [],
                )

                if not keys:
                    continue

                service = str(
                    keys[0]
                )

                amount = float(
                    group.get(
                        "Metrics",
                        {}
                    )
                    .get(
                        "UnblendedCost",
                        {}
                    )
                    .get(
                        "Amount",
                        0,
                    )
                    or 0
                )

                totals[service] = (
                    totals.get(
                        service,
                        0.0,
                    )
                    + amount
                )

        return [
            AWSServiceCost(
                service=service,
                amount=round(
                    amount,
                    6,
                ),
                currency="USD",
                start_date=start_date,
                end_date=end_date,
            )
            for service, amount
            in sorted(
                totals.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]

    def get_tagged_resources(
        self,
    ) -> list[AWSResource]:

        resources: list[AWSResource] = []

        paginator = self.tagging.get_paginator(
            "get_resources"
        )

        try:
            pages = paginator.paginate(
                ResourcesPerPage=100,
            )

            for page in pages:
                for item in page.get(
                    "ResourceTagMappingList",
                    [],
                ):
                    arn = str(
                        item.get(
                            "ResourceARN",
                            "",
                        )
                    )

                    if not arn:
                        continue

                    raw_type = self._resource_type_from_arn(
                        arn
                    )

                    tags = {
                        str(tag.get("Key")): str(tag.get("Value"))
                        for tag in item.get(
                            "Tags",
                            [],
                        )
                        if tag.get("Key") is not None
                    }

                    resources.append(
                        AWSResource(
                            resource_arn=arn,
                            resource_type=raw_type,
                            service=self._service_from_arn(
                                arn
                            ),
                            region=self.region,
                            tags=tags,
                            tagged=bool(tags),
                        )
                    )

        except (
            ClientError,
            BotoCoreError,
        ) as exc:
            raise AWSFinOpsError(
                "Unable to query AWS resource inventory: "
                f"{exc}"
            ) from exc

        return resources

    def collect_snapshot(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> AWSFinOpsSnapshot:

        account_id = self.get_account_id()

        service_costs = self.get_service_costs(
            start_date=start_date,
            end_date=end_date,
        )

        resources = self.get_tagged_resources()

        return AWSFinOpsSnapshot(
            account_id=account_id,
            region=self.region,
            cost_start_date=start_date,
            cost_end_date=end_date,
            service_costs=service_costs,
            resources=resources,
        )

    @staticmethod
    def default_date_range() -> tuple[str, str]:

        end = date.today()

        start = end - timedelta(
            days=7
        )

        return (
            start.isoformat(),
            end.isoformat(),
        )

    @staticmethod
    def _resource_type_from_arn(
        arn: str,
    ) -> ResourceType:

        if ":ec2:" in arn:
            return ResourceType.EC2

        if ":rds:" in arn:
            return ResourceType.RDS

        if ":ecr:" in arn:
            return ResourceType.ECR

        if ":s3:::" in arn:
            return ResourceType.S3

        if ":eks:" in arn:
            return ResourceType.EKS

        if (
            ":elasticloadbalancing:"
            in arn
        ):
            return ResourceType.LOAD_BALANCER

        return ResourceType.UNKNOWN

    @staticmethod
    def _service_from_arn(
        arn: str,
    ) -> str:

        parts = arn.split(":")

        if len(parts) >= 3:
            return parts[2]

        return "unknown"
