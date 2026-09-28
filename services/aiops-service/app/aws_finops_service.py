from __future__ import annotations

from .aws_finops_client import AWSFinOpsClient
from .finops_analyzer import FinOpsAnalyzer
from .finops_models import FinOpsReport


class AWSFinOpsService:

    def __init__(
        self,
        *,
        client: AWSFinOpsClient | None = None,
        analyzer: FinOpsAnalyzer | None = None,
    ) -> None:

        self.client = (
            client
            if client is not None
            else AWSFinOpsClient()
        )

        self.analyzer = (
            analyzer
            if analyzer is not None
            else FinOpsAnalyzer()
        )

    @staticmethod
    def default_date_range() -> tuple[str, str]:

        return AWSFinOpsClient.default_date_range()

    def generate_report(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> FinOpsReport:

        snapshot = self.client.collect_snapshot(
            start_date=start_date,
            end_date=end_date,
        )

        resources = []

        for resource in snapshot.resources:

            resources.append(
                {
                    "resource_id": resource.resource_arn,
                    "resource_type": (
                        resource.resource_type.value
                    ),
                    "service": resource.service,
                    "estimated_monthly_cost": 0.0,
                    "idle": False,
                    "tags": resource.tags,
                    "region": resource.region,
                }
            )

        report = self.analyzer.analyze(
            region=snapshot.region,
            account_id=snapshot.account_id,
            resources=resources,
        )

        report.cost_data_source = (
            "aws-cost-explorer"
        )

        return report
