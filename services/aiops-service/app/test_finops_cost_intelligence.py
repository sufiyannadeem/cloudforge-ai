from __future__ import annotations

from .finops_cost_intelligence import (
    BudgetStatus,
    CostAnomalySeverity,
    CostHistoryPoint,
    CostTrend,
    calculate_period_trend,
    detect_cost_anomalies,
)


def test_increasing_trend():
    result = calculate_period_trend(
        start_date="2026-09-01",
        end_date="2026-10-01",
        previous_start_date="2026-08-02",
        current_amount=120.0,
        previous_amount=100.0,
    )

    assert result.trend == CostTrend.INCREASING
    assert result.change_amount == 20.0
    assert result.change_percent == 20.0


def test_decreasing_trend():
    result = calculate_period_trend(
        start_date="2026-09-01",
        end_date="2026-10-01",
        previous_start_date="2026-08-02",
        current_amount=80.0,
        previous_amount=100.0,
    )

    assert result.trend == CostTrend.DECREASING
    assert result.change_percent == -20.0


def test_stable_trend():
    result = calculate_period_trend(
        start_date="2026-09-01",
        end_date="2026-10-01",
        previous_start_date="2026-08-02",
        current_amount=102.0,
        previous_amount=100.0,
    )

    assert result.trend == CostTrend.STABLE


def test_zero_baseline():
    result = calculate_period_trend(
        start_date="2026-09-01",
        end_date="2026-10-01",
        previous_start_date="2026-08-02",
        current_amount=10.0,
        previous_amount=0.0,
    )

    assert result.change_percent is None
    assert result.trend == CostTrend.INSUFFICIENT_DATA


def test_cost_anomaly_detection():
    points = [
        CostHistoryPoint(
            date=f"2026-09-{index:02d}",
            amount=1.0,
        )
        for index in range(1, 8)
    ]

    points.append(
        CostHistoryPoint(
            date="2026-09-08",
            amount=10.0,
        )
    )

    anomalies = detect_cost_anomalies(
        points=points,
        threshold=2.5,
        minimum_points=7,
    )

    assert len(anomalies) == 1
    assert anomalies[0].date == "2026-09-08"
    assert anomalies[0].severity == (
        CostAnomalySeverity.CRITICAL
    )


def test_insufficient_anomaly_history():
    points = [
        CostHistoryPoint(
            date=f"2026-09-{index:02d}",
            amount=1.0,
        )
        for index in range(1, 6)
    ]

    anomalies = detect_cost_anomalies(
        points=points,
        threshold=2.5,
        minimum_points=7,
    )

    assert anomalies == []




if __name__ == "__main__":
    test_increasing_trend()
    test_decreasing_trend()
    test_stable_trend()
    test_zero_baseline()
    test_cost_anomaly_detection()
    test_insufficient_anomaly_history()

    print(
        "ALL FINOPS COST INTELLIGENCE TESTS PASSED"
    )
