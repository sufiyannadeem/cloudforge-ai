from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .aws_finops_client import AWSFinOpsClient, AWSFinOpsError
from .finops_analyzer import FinOpsAnalyzer
from .finops_cost_intelligence import (
    BudgetResponse,
    BudgetStatus,
    BudgetSummary,
    CostAnomalyResponse,
    CostAttribution,
    CostAttributionResponse,
    CostHistoryPoint,
    CostHistoryResponse,
    CostTrendResponse,
    calculate_period_trend,
    default_cost_intelligence_range,
    detect_cost_anomalies,
    previous_period,
)
from .finops_models import AWSFinOpsSnapshot, ResourceType
from .finops_optimization_models import EC2Observation


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

    @staticmethod
    def default_cost_intelligence_range(
        days: int = 30,
    ) -> tuple[str, str]:
        return default_cost_intelligence_range(
            days
        )

    def generate_report(
        self,
        *,
        start_date: str,
        end_date: str,
    ):
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
                    "estimated_monthly_cost": None,
                    "actual_monthly_cost": None,
                    "cost_status": "unavailable",
                    "idle": None,
                    "utilization_status": "unavailable",
                    "tags": resource.tags,
                    "region": resource.region,
                }
            )

        report = self.analyzer.analyze(
            region=snapshot.region,
            account_id=snapshot.account_id,
            resources=resources,
        )

        report.resources = resources
        report.service_costs = snapshot.service_costs
        report.cost_data_source = (
            "aws-cost-explorer"
        )
        report.resource_data_source = (
            snapshot.resource_data_source
        )

        if snapshot.service_costs:
            report.summary.total_actual_monthly_cost = round(
                sum(c.amount for c in snapshot.service_costs),
                2,
            )

        return report

    def get_cost_history(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> CostHistoryResponse:
        raw_points = self.client.get_daily_cost_history(
            start_date=start_date,
            end_date=end_date,
        )

        points = [
            CostHistoryPoint(**point)
            for point in raw_points
        ]

        total = sum(
            point.amount
            for point in points
        )

        return CostHistoryResponse(
            start_date=start_date,
            end_date=end_date,
            total_cost=round(
                total,
                6,
            ),
            average_daily_cost=round(
                total / len(points),
                2,
            )
            if points
            else 0.0,
            points=points,
        )

    def get_cost_trend(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> CostTrendResponse:
        current = self.client.get_daily_cost_history(
            start_date=start_date,
            end_date=end_date,
        )

        previous_start, previous_end = (
            previous_period(
                start_date=start_date,
                end_date=end_date,
            )
        )

        previous = self.client.get_daily_cost_history(
            start_date=previous_start,
            end_date=previous_end,
        )

        current_amount = sum(
            float(point["amount"])
            for point in current
        )

        previous_amount = sum(
            float(point["amount"])
            for point in previous
        )

        return calculate_period_trend(
            start_date=start_date,
            end_date=end_date,
            previous_start_date=previous_start,
            current_amount=current_amount,
            previous_amount=previous_amount,
        )

    def get_cost_anomalies(
        self,
        *,
        start_date: str,
        end_date: str,
        threshold: float = 2.5,
    ) -> CostAnomalyResponse:
        raw_points = self.client.get_daily_cost_history(
            start_date=start_date,
            end_date=end_date,
        )

        points = [
            CostHistoryPoint(**point)
            for point in raw_points
        ]

        return detect_cost_anomalies(
            points=points,
            start_date=start_date,
            end_date=end_date,
            threshold=threshold,
        )

    def get_cost_attribution(
        self,
        *,
        start_date: str,
        end_date: str,
        dimension: str,
    ) -> CostAttributionResponse:
        normalized = dimension.strip().lower()

        tag_map = {
            "environment": "Environment",
            "project": "Project",
            "owner": "Owner",
            "costcenter": "CostCenter",
            "cost-center": "CostCenter",
        }

        if normalized == "service":
            costs = self.client.get_service_costs(
                start_date=start_date,
                end_date=end_date,
            )

            entries = [
                CostAttribution(
                    dimension="service",
                    value=item.service,
                    amount=item.amount,
                    currency=item.currency,
                )
                for item in costs
            ]
            entries.sort(key=lambda e: e.amount, reverse=True)
            return CostAttributionResponse(
                start_date=start_date,
                end_date=end_date,
                dimension="service",
                total_cost=round(
                    sum(
                        item.amount
                        for item in entries
                    ),
                    6,
                ),
                entries=entries,
            )

        if normalized in ("resource", "resource_id", "resource-id"):
            try:
                costs = self.client.get_resource_costs(
                    start_date=start_date,
                    end_date=end_date,
                )
                if not costs:
                    return CostAttributionResponse(
                        start_date=start_date,
                        end_date=end_date,
                        dimension="resource_id",
                        total_cost=0.0,
                        entries=[],
                        available=False,
                        status_message=(
                            "Resource-level cost attribution returned no records. "
                            "AWS Cost Explorer Hourly and Resource Level Data may not be enabled."
                        ),
                    )

                entries = [
                    CostAttribution(
                        dimension="resource_id",
                        value=str(item["resource_id"]),
                        amount=float(item["amount"]),
                        currency=str(item.get("currency", "USD")),
                    )
                    for item in costs
                ]
                entries.sort(key=lambda e: e.amount, reverse=True)
                return CostAttributionResponse(
                    start_date=start_date,
                    end_date=end_date,
                    dimension="resource_id",
                    total_cost=round(
                        sum(item.amount for item in entries),
                        6,
                    ),
                    entries=entries,
                    available=True,
                )
            except AWSFinOpsError as exc:
                return CostAttributionResponse(
                    start_date=start_date,
                    end_date=end_date,
                    dimension="resource_id",
                    total_cost=0.0,
                    entries=[],
                    available=False,
                    status_message=f"Resource-level cost attribution is unavailable: {exc}",
                )

        tag_key = tag_map.get(
            normalized
        )

        if tag_key is None:
            raise ValueError("Unsupported dimension")

        costs = self.client.get_tag_costs(
            start_date=start_date,
            end_date=end_date,
            tag_key=tag_key,
        )

        entries = [
            CostAttribution(
                dimension=normalized,
                value=str(item["value"]),
                amount=float(
                    item["amount"]
                ),
                currency=str(
                    item.get(
                        "currency",
                        "USD",
                    )
                ),
            )
            for item in costs
        ]

        return CostAttributionResponse(
            start_date=start_date,
            end_date=end_date,
            dimension=normalized,
            tag_key=tag_key,
            total_cost=round(
                sum(
                    item.amount
                    for item in entries
                ),
                6,
            ),
            entries=entries,
        )

    def get_budgets(self) -> BudgetResponse:
        account_id = self.client.get_account_id()

        raw_budgets = self.client.get_budgets(
            account_id=account_id,
        )

        summaries: list[BudgetSummary] = []

        for budget in raw_budgets:
            limit_data = budget.get(
                "BudgetLimit",
                {},
            )

            calculated = budget.get(
                "CalculatedSpend",
                {},
            )

            actual_data = calculated.get(
                "ActualSpend",
                {},
            )

            forecast_data = calculated.get(
                "ForecastedSpend",
                {},
            )

            limit = self._safe_float(
                limit_data.get("Amount")
            )

            actual = self._safe_float(
                actual_data.get("Amount")
            )

            forecast = self._safe_float(
                forecast_data.get("Amount")
            )

            actual_percent = (
                (actual / limit) * 100
                if actual is not None
                and limit
                and limit > 0
                else None
            )

            forecast_percent = (
                (forecast / limit) * 100
                if forecast is not None
                and limit
                and limit > 0
                else None
            )

            summaries.append(
                BudgetSummary(
                    name=str(
                        budget.get(
                            "BudgetName",
                            "unknown",
                        )
                    ),
                    budget_type=str(
                        budget.get(
                            "BudgetType",
                            "unknown",
                        )
                    ),
                    time_unit=str(
                        budget.get(
                            "TimeUnit",
                            "unknown",
                        )
                    ),
                    limit=limit,
                    actual_spend=actual,
                    forecasted_spend=forecast,
                    currency=str(
                        limit_data.get(
                            "Unit",
                            actual_data.get(
                                "Unit",
                                "USD",
                            ),
                        )
                    ),
                    actual_utilization_percent=(
                        round(
                            actual_percent,
                            4,
                        )
                        if actual_percent
                        is not None
                        else None
                    ),
                    forecast_utilization_percent=(
                        round(
                            forecast_percent,
                            4,
                        )
                        if forecast_percent
                        is not None
                        else None
                    ),
                    status=(
                        BudgetStatus.NO_BUDGET
                        if limit is None
                        else self._budget_status(
                            actual_percent,
                            forecast_percent,
                        )
                    ),
                    cost_filters=(
                        budget.get(
                            "CostFilters",
                            {},
                        )
                        or {}
                    ),
                )
            )

        return BudgetResponse(
            account_id=account_id,
            budgets=summaries,
        )

    @staticmethod
    def _safe_float(
        value: object,
    ) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _budget_status(
        actual_percent: float | None,
        forecast_percent: float | None,
    ) -> BudgetStatus:
        # Prioritize actual utilization; fall back to forecast if actual is missing.
        if actual_percent is not None:
            eval_percent = actual_percent
        elif forecast_percent is not None:
            eval_percent = forecast_percent
        else:
            return BudgetStatus.INSUFFICIENT_DATA

        if eval_percent > 100:
            return BudgetStatus.BREACHED
        if eval_percent >= 100:
            return BudgetStatus.CRITICAL
        if eval_percent >= 80:
            return BudgetStatus.WARNING
        if eval_percent >= 50:
            return BudgetStatus.HEALTHY
        return BudgetStatus.HEALTHY

    def get_ec2_utilization(
        self,
        *,
        instance_id: str,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        period_seconds: int = 3600,
        stat: str = "Average",
    ) -> dict[str, Any]:
        """
        Query real CloudWatch CPU utilization metrics for a given EC2 instance.
        """
        if start_time is None or end_time is None:
            now = datetime.now(timezone.utc)
            start_time = now - timedelta(days=7)
            end_time = now

        return self.client.get_ec2_cpu_utilization(
            instance_id=instance_id,
            start_time=start_time,
            end_time=end_time,
            period_seconds=period_seconds,
            stat=stat,
        )

    def collect_ec2_optimization_observations(
        self,
        *,
        snapshot: AWSFinOpsSnapshot | None = None,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        period_seconds: int = 3600,
    ) -> list[EC2Observation]:
        """
        Build EC2Observation instances using real CloudWatch metric observations.
        Missing CloudWatch telemetry is handled safely without inventing utilization data.
        """
        if snapshot is None:
            start_date, end_date = self.default_date_range()
            snapshot = self.client.collect_snapshot(
                start_date=start_date,
                end_date=end_date,
            )

        if start_time is None or end_time is None:
            now = datetime.now(timezone.utc)
            start_time = now - timedelta(days=7)
            end_time = now

        observations: list[EC2Observation] = []

        for resource in snapshot.resources:
            if resource.resource_type == ResourceType.EC2:
                arn = resource.resource_arn
                instance_id = arn.split("/")[-1] if "/" in arn else arn

                try:
                    metric_data = self.client.get_ec2_cpu_utilization(
                        instance_id=instance_id,
                        start_time=start_time,
                        end_time=end_time,
                        period_seconds=period_seconds,
                    )
                    cpu_pct = metric_data.get("cpu_utilization_percent")
                    util_available = bool(
                        metric_data.get("utilization_available", False)
                    )
                    dp_count = metric_data.get("datapoints_count")
                except AWSFinOpsError:
                    cpu_pct = None
                    util_available = False
                    dp_count = 0

                observations.append(
                    EC2Observation(
                        resource_id=instance_id,
                        cpu_utilization_percent=cpu_pct,
                        utilization_available=util_available,
                        period_seconds=period_seconds,
                        datapoints_count=dp_count,
                    )
                )

        return observations
