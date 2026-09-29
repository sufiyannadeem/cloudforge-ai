from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from math import sqrt
from statistics import mean, pstdev

from pydantic import BaseModel, Field


class CostTrend(str, Enum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient-data"


class CostAnomalySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CostHistoryPoint(BaseModel):
    date: str
    amount: float
    currency: str = "USD"


class CostHistoryResponse(BaseModel):
    start_date: str
    end_date: str
    currency: str = "USD"
    total_cost: float
    average_daily_cost: float
    points: list[CostHistoryPoint] = Field(default_factory=list)


class CostTrendResponse(BaseModel):
    start_date: str
    end_date: str
    comparison_start_date: str
    comparison_end_date: str
    current_cost: float
    previous_cost: float
    change_amount: float
    change_percent: float | None = None
    trend: CostTrend
    currency: str = "USD"


class CostAnomaly(BaseModel):
    date: str
    amount: float
    baseline_mean: float
    baseline_stddev: float
    z_score: float
    severity: CostAnomalySeverity
    reason: str


class CostAnomalyResponse(BaseModel):
    start_date: str
    end_date: str
    threshold: float
    anomalies: list[CostAnomaly] = Field(default_factory=list)


class CostAttribution(BaseModel):
    dimension: str
    value: str
    amount: float
    currency: str = "USD"


class CostAttributionResponse(BaseModel):
    start_date: str
    end_date: str
    dimension: str
    tag_key: str | None = None
    total_cost: float
    entries: list[CostAttribution] = Field(default_factory=list)


class BudgetStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    NO_BUDGET = "no-budget"
    INSUFFICIENT_DATA = "insufficient-data"


class BudgetSummary(BaseModel):
    name: str
    budget_type: str
    time_unit: str
    limit: float | None = None
    actual_spend: float | None = None
    forecasted_spend: float | None = None
    currency: str = "USD"
    actual_utilization_percent: float | None = None
    forecast_utilization_percent: float | None = None
    status: BudgetStatus
    cost_filters: dict[str, list[str]] = Field(default_factory=dict)


class BudgetResponse(BaseModel):
    account_id: str
    budgets: list[BudgetSummary] = Field(default_factory=list)


def calculate_trend(
    *,
    start_date: str,
    end_date: str,
    daily_amounts: list[float],
) -> CostTrendResponse:
    current_cost = round(sum(daily_amounts), 6)

    days = len(daily_amounts)

    if days < 2:
        return CostTrendResponse(
            start_date=start_date,
            end_date=end_date,
            comparison_start_date="",
            comparison_end_date=start_date,
            current_cost=current_cost,
            previous_cost=0.0,
            change_amount=0.0,
            change_percent=None,
            trend=CostTrend.INSUFFICIENT_DATA,
        )

    current_average = current_cost / days

    # This function receives only the current period.
    # Previous-period comparison is performed by
    # calculate_period_trend below.
    return CostTrendResponse(
        start_date=start_date,
        end_date=end_date,
        comparison_start_date="",
        comparison_end_date=start_date,
        current_cost=current_cost,
        previous_cost=0.0,
        change_amount=0.0,
        change_percent=None,
        trend=(
            CostTrend.STABLE
            if current_average == 0
            else CostTrend.INSUFFICIENT_DATA
        ),
    )


def calculate_period_trend(
    *,
    start_date: str,
    end_date: str,
    previous_start_date: str,
    current_amount: float,
    previous_amount: float,
    stable_threshold_percent: float = 5.0,
) -> CostTrendResponse:
    change_amount = current_amount - previous_amount

    if previous_amount == 0:
        change_percent = None
        trend = (
            CostTrend.STABLE
            if current_amount == 0
            else CostTrend.INSUFFICIENT_DATA
        )
    else:
        change_percent = (
            change_amount / previous_amount
        ) * 100.0

        if abs(change_percent) < stable_threshold_percent:
            trend = CostTrend.STABLE
        elif change_percent > 0:
            trend = CostTrend.INCREASING
        else:
            trend = CostTrend.DECREASING

    return CostTrendResponse(
        start_date=start_date,
        end_date=end_date,
        comparison_start_date=previous_start_date,
        comparison_end_date=start_date,
        current_cost=round(current_amount, 6),
        previous_cost=round(previous_amount, 6),
        change_amount=round(change_amount, 6),
        change_percent=(
            round(change_percent, 4)
            if change_percent is not None
            else None
        ),
        trend=trend,
    )


def detect_cost_anomalies(
    *,
    points: list[CostHistoryPoint],
    threshold: float = 2.5,
    minimum_points: int = 7,
) -> list[CostAnomaly]:
    if len(points) < minimum_points:
        return []

    values = [point.amount for point in points]

    anomalies: list[CostAnomaly] = []

    for index, point in enumerate(points):
        history = values[:index]

        if len(history) < minimum_points:
            continue

        baseline_mean = mean(history)
        baseline_stddev = pstdev(history)

        if baseline_stddev == 0:
            if point.amount <= baseline_mean:
                continue

            z_score = (
                float("inf")
                if point.amount > baseline_mean
                else 0.0
            )
        else:
            z_score = (
                point.amount - baseline_mean
            ) / baseline_stddev

        if z_score < threshold:
            continue

        severity = (
            CostAnomalySeverity.CRITICAL
            if z_score >= 4.0
            else CostAnomalySeverity.WARNING
        )

        anomalies.append(
            CostAnomaly(
                date=point.date,
                amount=round(point.amount, 6),
                baseline_mean=round(
                    baseline_mean,
                    6,
                ),
                baseline_stddev=round(
                    baseline_stddev,
                    6,
                ),
                z_score=round(
                    z_score,
                    4,
                ),
                severity=severity,
                reason=(
                    "Daily AWS cost is materially above "
                    "the historical baseline."
                ),
            )
        )

    return anomalies


def default_cost_intelligence_range(
    days: int = 30,
) -> tuple[str, str]:
    days = max(1, min(days, 365))

    end = date.today()
    start = end - timedelta(days=days)

    return (
        start.isoformat(),
        end.isoformat(),
    )


def previous_period(
    *,
    start_date: str,
    end_date: str,
) -> tuple[str, str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    duration = end - start

    previous_end = start
    previous_start = start - duration

    return (
        previous_start.isoformat(),
        previous_end.isoformat(),
    )


def budget_status(
    *,
    actual_percent: float | None,
    forecast_percent: float | None,
) -> BudgetStatus:
    values = [
        value
        for value in (
            actual_percent,
            forecast_percent,
        )
        if value is not None
    ]

    if not values:
        return BudgetStatus.INSUFFICIENT_DATA

    maximum = max(values)

    if maximum >= 100:
        return BudgetStatus.CRITICAL

    if maximum >= 80:
        return BudgetStatus.WARNING

    return BudgetStatus.HEALTHY
