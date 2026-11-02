from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from botocore.exceptions import ClientError

from .aws_finops_client import AWSFinOpsClient, AWSFinOpsError
from .aws_finops_service import AWSFinOpsService
from .finops_cost_intelligence import (
    BudgetStatus,
    CostTrend,
    calculate_period_trend,
    detect_cost_anomalies,
)
from .finops_models import (
    AWSFinOpsSnapshot,
    AWSResource,
    AWSServiceCost,
    ResourceType,
)


def test_cost_history_calculation():
    client = MagicMock()
    client.get_daily_cost_history.return_value = [
        {"date": "2026-10-01", "amount": 10.50, "currency": "USD"},
        {"date": "2026-10-02", "amount": 12.25, "currency": "USD"},
        {"date": "2026-10-03", "amount": 9.25, "currency": "USD"},
    ]
    service = AWSFinOpsService(client=client)

    history = service.get_cost_history(start_date="2026-10-01", end_date="2026-10-04")

    assert history.total_cost == 32.00
    assert history.average_daily_cost == 10.67
    assert len(history.points) == 3
    assert history.currency == "USD"


def test_cost_history_empty_data():
    client = MagicMock()
    client.get_daily_cost_history.return_value = []
    service = AWSFinOpsService(client=client)

    history = service.get_cost_history(start_date="2026-10-01", end_date="2026-10-04")

    assert history.total_cost == 0.0
    assert history.average_daily_cost == 0.0
    assert history.points == []


def test_cost_trend_calculation_stable_and_division_by_zero():
    trend_zero = calculate_period_trend(
        current_cost=0.0,
        previous_cost=0.0,
        start_date="2026-10-01",
        end_date="2026-10-10",
        comparison_start_date="2026-09-21",
        comparison_end_date="2026-10-01",
    )
    assert trend_zero.change_amount == 0.0
    assert trend_zero.change_percent is None
    assert trend_zero.trend == CostTrend.STABLE

    trend_up = calculate_period_trend(
        current_cost=150.0,
        previous_cost=100.0,
        start_date="2026-10-01",
        end_date="2026-10-10",
        comparison_start_date="2026-09-21",
        comparison_end_date="2026-10-01",
    )
    assert trend_up.change_amount == 50.0
    assert trend_up.change_percent == 50.0
    assert trend_up.trend == CostTrend.WORSENING


def test_cost_anomalies_detection():
    # Stable points: mean=10, stddev=0
    stable_points = [
        {"date": f"2026-10-0{i}", "amount": 10.0, "currency": "USD"}
        for i in range(1, 8)
    ]
    anomalies = detect_cost_anomalies(
        points=stable_points,
        start_date="2026-10-01",
        end_date="2026-10-08",
        threshold=2.5,
    )
    assert anomalies.anomalies == []

    # One extreme outlier spike
    spike_points = stable_points + [
        {"date": "2026-10-08", "amount": 100.0, "currency": "USD"}
    ]
    anomalies_spiked = detect_cost_anomalies(
        points=spike_points,
        start_date="2026-10-01",
        end_date="2026-10-09",
        threshold=2.0,
    )
    assert len(anomalies_spiked.anomalies) >= 1
    assert anomalies_spiked.anomalies[0].date == "2026-10-08"
    assert anomalies_spiked.anomalies[0].amount == 100.0


def test_cost_attribution_service_and_rejection():
    client = MagicMock()
    client.get_service_costs.return_value = [
        AWSServiceCost(service="Amazon S3", amount=5.0, start_date="2026-10-01", end_date="2026-10-10"),
        AWSServiceCost(service="Amazon EC2", amount=25.0, start_date="2026-10-01", end_date="2026-10-10"),
    ]
    service = AWSFinOpsService(client=client)

    attribution = service.get_cost_attribution(
        start_date="2026-10-01",
        end_date="2026-10-10",
        dimension="service",
    )
    assert attribution.total_cost == 30.0
    assert len(attribution.entries) == 2
    # Verify sorted descending by amount
    assert attribution.entries[0].value == "Amazon EC2"
    assert attribution.entries[0].amount == 25.0
    assert attribution.entries[1].value == "Amazon S3"
    assert attribution.entries[1].amount == 5.0

    # Invalid dimension raises ValueError
    with pytest.raises(ValueError, match="Unsupported dimension"):
        service.get_cost_attribution(
            start_date="2026-10-01",
            end_date="2026-10-10",
            dimension="unsupported_dim",
        )


def test_get_budgets_status_and_utilization():
    client = MagicMock()
    client.get_account_id.return_value = "111122223333"
    client.get_budgets.return_value = [
        {
            "BudgetName": "DevBudget",
            "BudgetType": "COST",
            "TimeUnit": "MONTHLY",
            "BudgetLimit": {"Amount": "100.0", "Unit": "USD"},
            "CalculatedSpend": {
                "ActualSpend": {"Amount": "50.0", "Unit": "USD"},
                "ForecastedSpend": {"Amount": "80.0", "Unit": "USD"},
            },
            "CostFilters": {},
        },
        {
            "BudgetName": "OverspendBudget",
            "BudgetType": "COST",
            "TimeUnit": "MONTHLY",
            "BudgetLimit": {"Amount": "100.0", "Unit": "USD"},
            "CalculatedSpend": {
                "ActualSpend": {"Amount": "110.0", "Unit": "USD"},
            },
            "CostFilters": {},
        },
    ]
    service = AWSFinOpsService(client=client)

    budgets_resp = service.get_budgets()
    assert budgets_resp.account_id == "111122223333"
    assert len(budgets_resp.budgets) == 2

    b1 = budgets_resp.budgets[0]
    assert b1.name == "DevBudget"
    assert b1.actual_utilization_percent == 50.0
    assert b1.status == BudgetStatus.HEALTHY

    b2 = budgets_resp.budgets[1]
    assert b2.name == "OverspendBudget"
    assert b2.actual_utilization_percent == 110.0
    assert b2.status == BudgetStatus.BREACHED


def test_aws_client_error_propagation():
    client = MagicMock()
    client.collect_snapshot.side_effect = AWSFinOpsError("AccessDeniedException: User is not authorized")

    service = AWSFinOpsService(client=client)
    with pytest.raises(AWSFinOpsError, match="AccessDeniedException"):
        service.generate_report(start_date="2026-10-01", end_date="2026-10-08")


def test_report_data_source_explicit_tagging():
    client = MagicMock()
    client.collect_snapshot.return_value = AWSFinOpsSnapshot(
        account_id="999888777666",
        region="us-east-1",
        cost_start_date="2026-10-01",
        cost_end_date="2026-10-08",
        service_costs=[],
        resources=[],
    )
    service = AWSFinOpsService(client=client)
    report = service.generate_report(start_date="2026-10-01", end_date="2026-10-08")

    assert report.cost_data_source == "aws-cost-explorer"
    assert report.account_id == "999888777666"
    assert report.summary.total_estimated_monthly_cost == 0.0
