from __future__ import annotations

import math

from .anomaly_models import AnomalyClassification
from .anomaly_service import AnomalyDetectionService


def test_mean() -> None:
    assert (
        AnomalyDetectionService._mean(
            [10.0, 20.0, 30.0]
        )
        == 20.0
    )


def test_population_stddev() -> None:
    result = AnomalyDetectionService._population_stddev(
        [10.0, 20.0, 30.0]
    )

    assert math.isclose(
        result,
        8.1649658,
        rel_tol=1e-6,
    )


def test_relative_deviation() -> None:
    result = AnomalyDetectionService._relative_deviation(
        current_value=200.0,
        baseline=100.0,
    )

    assert result == 100.0


def test_z_score() -> None:
    result = AnomalyDetectionService._z_score(
        current_value=130.0,
        baseline=100.0,
        standard_deviation=10.0,
    )

    assert result == 3.0


def test_direction_increase() -> None:
    result = AnomalyDetectionService._direction(
        current_value=120.0,
        baseline=100.0,
    )

    assert result.value == "increase"


def test_direction_decrease() -> None:
    result = AnomalyDetectionService._direction(
        current_value=80.0,
        baseline=100.0,
    )

    assert result.value == "decrease"


def test_request_rate_large_change_is_critical() -> None:
    service = AnomalyDetectionService()

    definition = next(
        item
        for item in service._definitions()
        if item.name == "request_rate"
    )

    result = service._classify(
        definition=definition,
        current_value=300.0,
        baseline=100.0,
        deviation_percent=200.0,
        z_score=3.5,
    )

    assert (
        result
        == AnomalyClassification.CRITICAL
    )


def test_error_rate_increase_is_anomaly() -> None:
    service = AnomalyDetectionService()

    definition = next(
        item
        for item in service._definitions()
        if item.name == "error_rate"
    )

    result = service._classify(
        definition=definition,
        current_value=4.0,
        baseline=2.0,
        deviation_percent=100.0,
        z_score=2.2,
    )

    assert (
        result
        == AnomalyClassification.ANOMALY
    )


def test_error_rate_decrease_is_not_anomaly() -> None:
    service = AnomalyDetectionService()

    definition = next(
        item
        for item in service._definitions()
        if item.name == "error_rate"
    )

    result = service._classify(
        definition=definition,
        current_value=1.0,
        baseline=2.0,
        deviation_percent=50.0,
        z_score=-2.5,
    )

    assert (
        result
        == AnomalyClassification.NORMAL
    )


def test_latency_increase_can_be_critical() -> None:
    service = AnomalyDetectionService()

    definition = next(
        item
        for item in service._definitions()
        if item.name == "p95_latency"
    )

    result = service._classify(
        definition=definition,
        current_value=1.82,
        baseline=0.42,
        deviation_percent=333.33,
        z_score=3.5,
    )

    assert (
        result
        == AnomalyClassification.CRITICAL
    )


def test_availability_drop_is_anomaly() -> None:
    service = AnomalyDetectionService()

    definition = next(
        item
        for item in service._definitions()
        if item.name == "availability"
    )

    result = service._classify(
        definition=definition,
        current_value=90.0,
        baseline=100.0,
        deviation_percent=10.0,
        z_score=-2.5,
    )

    assert (
        result
        == AnomalyClassification.ANOMALY
    )


def test_availability_increase_is_not_anomaly() -> None:
    service = AnomalyDetectionService()

    definition = next(
        item
        for item in service._definitions()
        if item.name == "availability"
    )

    result = service._classify(
        definition=definition,
        current_value=100.0,
        baseline=90.0,
        deviation_percent=11.11,
        z_score=2.5,
    )

    assert (
        result
        == AnomalyClassification.NORMAL
    
    )


def test_partial_insufficient_data_is_insufficient() -> None:
    result = AnomalyDetectionService._classify_overall(
        normal_count=3,
        anomaly_count=0,
        critical_count=0,
        insufficient_count=1,
        total_count=4,
    )

    assert result == AnomalyClassification.INSUFFICIENT_DATA


def test_all_metrics_insufficient_is_insufficient() -> None:
    result = AnomalyDetectionService._classify_overall(
        normal_count=0,
        anomaly_count=0,
        critical_count=0,
        insufficient_count=4,
        total_count=4,
    )

    assert result == AnomalyClassification.INSUFFICIENT_DATA


def test_critical_takes_priority() -> None:
    result = AnomalyDetectionService._classify_overall(
        normal_count=2,
        anomaly_count=1,
        critical_count=1,
        insufficient_count=0,
        total_count=4,
    )

    assert result == AnomalyClassification.CRITICAL


def test_anomaly_takes_priority_over_insufficient_data() -> None:
    result = AnomalyDetectionService._classify_overall(
        normal_count=2,
        anomaly_count=1,
        critical_count=0,
        insufficient_count=1,
        total_count=4,
    )

    assert result == AnomalyClassification.ANOMALY


def test_all_normal_is_normal() -> None:
    result = AnomalyDetectionService._classify_overall(
        normal_count=4,
        anomaly_count=0,
        critical_count=0,
        insufficient_count=0,
        total_count=4,
    )

    assert result == AnomalyClassification.NORMAL


class FakePrometheusClient:
    def __init__(
        self,
        values: list[float],
    ) -> None:
        self.values = values

    def range_values(
        self,
        *,
        expression: str,
        start_timestamp: float,
        end_timestamp: float,
        step_seconds: int,
    ) -> tuple[list[tuple[float, float]], None]:
        return (
            [
                (float(index), value)
                for index, value in enumerate(self.values)
            ],
            None,
        )


def test_latency_pipeline_detects_critical_anomaly() -> None:
    historical_values = [0.42] * 60
    current_value = 1.82

    prometheus = FakePrometheusClient(
        historical_values + [current_value]
    )

    service = AnomalyDetectionService(
        prometheus_client=prometheus
    )

    definition = next(
        item
        for item in service._definitions()
        if item.name == "p95_latency"
    )

    result = service._evaluate_metric(
        definition=definition,
        service="deployment-service",
        start_timestamp=0.0,
        end_timestamp=3600.0,
        step_seconds=60,
    )

    assert result.current_value == 1.82
    assert result.baseline_value == 0.42
    assert result.deviation_percent > 300.0
    assert result.classification == AnomalyClassification.CRITICAL
