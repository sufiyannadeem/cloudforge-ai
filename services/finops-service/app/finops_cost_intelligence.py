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
    WORSENING = "worsening"


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
    BREACHED = "breached"
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
    previous_start_date: str | None = None,
    comparison_start_date: str | None = None,
    comparison_end_date: str | None = None,
    current_amount: float | None = None,
    previous_amount: float | None = None,
    current_cost: float | None = None,
    previous_cost: float | None = None,
    stable_threshold_percent: float = 5.0,
) -> CostTrendResponse:
    # Resolve aliases: prefer explicit cost if provided, otherwise amount.
    cur = current_cost if current_cost is not None else current_amount
    prev = previous_cost if previous_cost is not None else previous_amount
    # Treat missing values as zero.
    cur = 0.0 if cur is None else cur
    prev = 0.0 if prev is None else prev
    change_amount = cur - prev
    # Determine if cost fields are used (legacy API)
    using_cost_fields = current_cost is not None or previous_cost is not None
    change_amount = cur - prev
    if prev == 0:
        change_percent = None
        trend = (
            CostTrend.STABLE
            if cur == 0
            else CostTrend.INSUFFICIENT_DATA
        )
    else:
        change_percent = (change_amount / prev) * 100.0
        if change_percent > 0:
            if using_cost_fields:
                # Legacy behavior: any increase considered worsening
                trend = CostTrend.WORSENING
            else:
                # New behavior: apply stable threshold
                if change_percent >= stable_threshold_percent:
                    trend = CostTrend.INCREASING
                else:
                    trend = CostTrend.STABLE
        else:
            trend = CostTrend.DECREASING
    return CostTrendResponse(
        start_date=start_date,
        end_date=end_date,
        comparison_start_date=comparison_start_date or previous_start_date,
        comparison_end_date=comparison_end_date or start_date,
        current_cost=round(cur, 6),
        previous_cost=round(prev, 6),
        change_amount=round(change_amount, 6),
        change_percent=(
            round(change_percent, 4) if change_percent is not None else None
        ),
        trend=trend,
    )



def detect_cost_anomalies(
    *,
    points: list[CostHistoryPoint] | list[dict],
    start_date: str | None = None,
    end_date: str | None = None,
    threshold: float = 2.5,
    minimum_points: int = 7,
) -> CostAnomalyResponse | list[CostAnomaly]:
    """Detect cost anomalies in a series of CostHistoryPoints.

    Accepts a list of ``CostHistoryPoint`` objects or plain dictionaries for
    backward‑compatible callers. If ``start_date``/``end_date`` are omitted the
    function returns a plain list of ``CostAnomaly``; otherwise it returns a
    ``CostAnomalyResponse`` wrapping the list.
    """
    # Normalise input to CostHistoryPoint instances.
    normalized: list[CostHistoryPoint] = []
    for pt in points:
        if isinstance(pt, CostHistoryPoint):
            normalized.append(pt)
        else:
            normalized.append(CostHistoryPoint(**pt))

    if len(normalized) < minimum_points:
        anomalies: list[CostAnomaly] = []
    else:
        values = [p.amount for p in normalized]
        anomalies = []
        for index, point in enumerate(normalized):
            history = values[:index]
            if len(history) < minimum_points:
                continue
            baseline_mean = mean(history)
            baseline_stddev = pstdev(history)
            if baseline_stddev == 0:
                if point.amount <= baseline_mean:
                    continue
                z_score = float("inf") if point.amount > baseline_mean else 0.0
            else:
                z_score = (point.amount - baseline_mean) / baseline_stddev
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
                    baseline_mean=round(baseline_mean, 6),
                    baseline_stddev=round(baseline_stddev, 6),
                    z_score=round(z_score, 4),
                    severity=severity,
                    reason=(
                        "Daily AWS cost is materially above "
                        "the historical baseline."
                    ),
                )
            )
    if start_date is None and end_date is None:
        return anomalies
    return CostAnomalyResponse(
        start_date=start_date or "",
        end_date=end_date or "",
        threshold=threshold,
        anomalies=anomalies,
    )


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
