from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .anomaly_models import (
    AnomalyClassification,
    AnomalyDirection,
    AnomalyMetric,
    AnomalySummary,
)
from .prometheus_client import PrometheusClient


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    display_name: str
    unit: str
    expression: Callable[[str], str]
    bad_direction: str


class AnomalyDetectionService:
    """
    Explainable statistical anomaly detection for CloudForge.

    The detector intentionally uses statistical baselines instead
    of opaque ML models.

    Current implementation:
        baseline = arithmetic mean
        dispersion = population standard deviation
        z-score = (current - mean) / stddev

    Classification combines z-score and relative deviation.

    This produces evidence that can be directly shown to an operator.
    """

    MINIMUM_SAMPLES = 5

    ANOMALY_Z_SCORE = 2.0
    CRITICAL_Z_SCORE = 3.0

    ANOMALY_DEVIATION_PERCENT = 50.0
    CRITICAL_DEVIATION_PERCENT = 200.0

    def __init__(
        self,
        prometheus_client: PrometheusClient | None = None,
    ) -> None:
        self.prometheus = (
            prometheus_client
            or PrometheusClient()
        )

    def evaluate(
        self,
        service: str = "deployment-service",
        window_minutes: int = 60,
        step_seconds: int = 60,
    ) -> AnomalySummary:
        if window_minutes < 5:
            raise ValueError(
                "window_minutes must be at least 5"
            )

        if window_minutes > 24 * 60:
            raise ValueError(
                "window_minutes cannot exceed 1440"
            )

        if step_seconds < 15:
            raise ValueError(
                "step_seconds must be at least 15"
            )

        now = datetime.now(timezone.utc)

        end_timestamp = now.timestamp()
        start_timestamp = (
            now - timedelta(minutes=window_minutes)
        ).timestamp()

        metrics: list[AnomalyMetric] = []

        for definition in self._definitions():
            metric = self._evaluate_metric(
                definition=definition,
                service=service,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                step_seconds=step_seconds,
            )

            metrics.append(metric)

        normal_count = sum(
            metric.classification
            == AnomalyClassification.NORMAL
            for metric in metrics
        )

        anomaly_count = sum(
            metric.classification
            == AnomalyClassification.ANOMALY
            for metric in metrics
        )

        critical_count = sum(
            metric.classification
            == AnomalyClassification.CRITICAL
            for metric in metrics
        )

        insufficient_count = sum(
            metric.classification
            == AnomalyClassification.INSUFFICIENT_DATA
            for metric in metrics
        )

        overall = self._classify_overall(
            normal_count=normal_count,
            anomaly_count=anomaly_count,
            critical_count=critical_count,
            insufficient_count=insufficient_count,
            total_count=len(metrics),
        )

        return AnomalySummary(
            service=service,
            window_minutes=window_minutes,
            step_seconds=step_seconds,
            overall_classification=overall,
            normal_count=normal_count,
            anomaly_count=anomaly_count,
            critical_count=critical_count,
            insufficient_data_count=insufficient_count,
            metrics=metrics,
            generated_at=now,
        )

    @staticmethod
    def _classify_overall(
        *,
        normal_count: int,
        anomaly_count: int,
        critical_count: int,
        insufficient_count: int,
        total_count: int,
    ) -> AnomalyClassification:
        """
        Determine the overall anomaly state from individual metrics.

        Priority:
            1. CRITICAL
            2. ANOMALY
            3. INSUFFICIENT_DATA
            4. NORMAL

        Partial telemetry loss must not be reported as
        an anomaly when no metric is actually anomalous.
        """

        if critical_count > 0:
            return AnomalyClassification.CRITICAL

        if anomaly_count > 0:
            return AnomalyClassification.ANOMALY

        if insufficient_count > 0:
            return AnomalyClassification.INSUFFICIENT_DATA

        if total_count == 0:
            return AnomalyClassification.INSUFFICIENT_DATA

        return AnomalyClassification.NORMAL


    def _evaluate_metric(
        self,
        definition: MetricDefinition,
        service: str,
        start_timestamp: float,
        end_timestamp: float,
        step_seconds: int,
    ) -> AnomalyMetric:
        expression = definition.expression(
            self._escape_label(service)
        )

        values, error = self.prometheus.range_values(
            expression=expression,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            step_seconds=step_seconds,
        )

        if error:
            return AnomalyMetric(
                name=definition.name,
                display_name=definition.display_name,
                unit=definition.unit,
                classification=(
                    AnomalyClassification.INSUFFICIENT_DATA
                ),
                evidence=[
                    f"Prometheus query failed: {error}"
                ],
                sample_count=0,
            )

        numeric_values = [
            value
            for _, value in values
            if math.isfinite(value)
        ]

        if len(numeric_values) < self.MINIMUM_SAMPLES:
            return AnomalyMetric(
                name=definition.name,
                display_name=definition.display_name,
                unit=definition.unit,
                classification=(
                    AnomalyClassification.INSUFFICIENT_DATA
                ),
                evidence=[
                    (
                        f"Only {len(numeric_values)} historical "
                        f"samples were available; at least "
                        f"{self.MINIMUM_SAMPLES} are required."
                    )
                ],
                sample_count=len(numeric_values),
            )

        current_value = numeric_values[-1]

        historical_values = numeric_values[:-1]

        if len(historical_values) < 3:
            return AnomalyMetric(
                name=definition.name,
                display_name=definition.display_name,
                unit=definition.unit,
                current_value=current_value,
                classification=(
                    AnomalyClassification.INSUFFICIENT_DATA
                ),
                evidence=[
                    "Not enough historical observations for a baseline."
                ],
                sample_count=len(numeric_values),
            )

        baseline = self._mean(historical_values)
        standard_deviation = self._population_stddev(
            historical_values
        )

        deviation_percent = self._relative_deviation(
            current_value=current_value,
            baseline=baseline,
        )

        z_score = self._z_score(
            current_value=current_value,
            baseline=baseline,
            standard_deviation=standard_deviation,
        )

        direction = self._direction(
            current_value=current_value,
            baseline=baseline,
        )

        classification = self._classify(
            definition=definition,
            current_value=current_value,
            baseline=baseline,
            deviation_percent=deviation_percent,
            z_score=z_score,
        )

        evidence = self._build_evidence(
            definition=definition,
            current_value=current_value,
            baseline=baseline,
            standard_deviation=standard_deviation,
            deviation_percent=deviation_percent,
            z_score=z_score,
            direction=direction,
            classification=classification,
        )

        return AnomalyMetric(
            name=definition.name,
            display_name=definition.display_name,
            unit=definition.unit,
            current_value=current_value,
            baseline_value=baseline,
            standard_deviation=standard_deviation,
            z_score=z_score,
            deviation_percent=deviation_percent,
            direction=direction,
            classification=classification,
            evidence=evidence,
            sample_count=len(numeric_values),
        )

    def _classify(
        self,
        definition: MetricDefinition,
        current_value: float,
        baseline: float,
        deviation_percent: float,
        z_score: float,
    ) -> AnomalyClassification:
        absolute_z = abs(z_score)

        if definition.name == "availability":
            # Availability is anomalous when it falls.
            harmful_change = baseline - current_value

            if (
                harmful_change > 0
                and (
                    absolute_z >= self.CRITICAL_Z_SCORE
                    or deviation_percent
                    >= self.CRITICAL_DEVIATION_PERCENT
                )
            ):
                return AnomalyClassification.CRITICAL

            if (
                harmful_change > 0
                and (
                    absolute_z >= self.ANOMALY_Z_SCORE
                    or deviation_percent
                    >= self.ANOMALY_DEVIATION_PERCENT
                )
            ):
                return AnomalyClassification.ANOMALY

            return AnomalyClassification.NORMAL

        if definition.name == "request_rate":
            # Request traffic can legitimately increase or decrease.
            # Large deviations in either direction are anomalous.
            if (
                absolute_z >= self.CRITICAL_Z_SCORE
                or deviation_percent
                >= self.CRITICAL_DEVIATION_PERCENT
            ):
                return AnomalyClassification.CRITICAL

            if (
                absolute_z >= self.ANOMALY_Z_SCORE
                or deviation_percent
                >= self.ANOMALY_DEVIATION_PERCENT
            ):
                return AnomalyClassification.ANOMALY

            return AnomalyClassification.NORMAL

        # Error rate and latency are primarily bad when increasing.
        harmful_change = current_value - baseline

        if (
            harmful_change > 0
            and (
                absolute_z >= self.CRITICAL_Z_SCORE
                or deviation_percent
                >= self.CRITICAL_DEVIATION_PERCENT
            )
        ):
            return AnomalyClassification.CRITICAL

        if (
            harmful_change > 0
            and (
                absolute_z >= self.ANOMALY_Z_SCORE
                or deviation_percent
                >= self.ANOMALY_DEVIATION_PERCENT
            )
        ):
            return AnomalyClassification.ANOMALY

        return AnomalyClassification.NORMAL

    @staticmethod
    def _build_evidence(
        definition: MetricDefinition,
        current_value: float,
        baseline: float,
        standard_deviation: float,
        deviation_percent: float,
        z_score: float,
        direction: AnomalyDirection,
        classification: AnomalyClassification,
    ) -> list[str]:
        evidence = [
            (
                f"Current {definition.display_name.lower()} is "
                f"{AnomalyDetectionService._format_value(current_value, definition.unit)}."
            ),
            (
                f"Historical baseline is "
                f"{AnomalyDetectionService._format_value(baseline, definition.unit)}."
            ),
            (
                f"Observed deviation is "
                f"{deviation_percent:.1f}% "
                f"({direction.value})."
            ),
        ]

        if standard_deviation > 0:
            evidence.append(
                f"Z-score is {z_score:.2f}."
            )
        else:
            evidence.append(
                "Historical standard deviation is approximately zero."
            )

        evidence.append(
            f"Classification is {classification.value}."
        )

        return evidence

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values)

    @staticmethod
    def _population_stddev(
        values: list[float],
    ) -> float:
        mean = AnomalyDetectionService._mean(values)

        variance = sum(
            (value - mean) ** 2
            for value in values
        ) / len(values)

        return math.sqrt(variance)

    @staticmethod
    def _relative_deviation(
        current_value: float,
        baseline: float,
    ) -> float:
        denominator = max(abs(baseline), 1e-9)

        return (
            abs(current_value - baseline)
            / denominator
        ) * 100.0

    @staticmethod
    def _z_score(
        current_value: float,
        baseline: float,
        standard_deviation: float,
    ) -> float:
        if standard_deviation <= 1e-9:
            if math.isclose(
                current_value,
                baseline,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                return 0.0

            return math.inf if current_value > baseline else -math.inf

        return (
            current_value - baseline
        ) / standard_deviation

    @staticmethod
    def _direction(
        current_value: float,
        baseline: float,
    ) -> AnomalyDirection:
        if math.isclose(
            current_value,
            baseline,
            rel_tol=1e-6,
            abs_tol=1e-9,
        ):
            return AnomalyDirection.STABLE

        if current_value > baseline:
            return AnomalyDirection.INCREASE

        return AnomalyDirection.DECREASE

    @staticmethod
    def _format_value(
        value: float,
        unit: str,
    ) -> str:
        if unit == "seconds":
            return f"{value:.3f}s"

        if unit == "percent":
            return f"{value:.2f}%"

        if unit == "requests_per_second":
            return f"{value:.2f} req/s"

        return f"{value:.3f}"

    @staticmethod
    def _definitions() -> list[MetricDefinition]:
        return [
            MetricDefinition(
                name="request_rate",
                display_name="Request rate",
                unit="requests_per_second",
                bad_direction="both",
                expression=lambda service: (
                    "sum("
                    "rate(http_requests_total{"
                    f'job="{service}"'
                    "}[5m])"
                    ")"
                ),
            ),
            MetricDefinition(
                name="error_rate",
                display_name="Error rate",
                unit="percent",
                bad_direction="increase",
                expression=lambda service: (
                    "100 * ("
                    "("
                    "sum(rate(http_requests_total{"
                    f'job="{service}",status=~"5.."'
                    "}[5m]))"
                    " or vector(0)"
                    ")"
                    " / clamp_min("
                    "sum(rate(http_requests_total{"
                    f'job="{service}"'
                    "}[5m])),"
                    "0.001)"
                    ")"
                ),
            ),
            MetricDefinition(
                name="p95_latency",
                display_name="P95 latency",
                unit="seconds",
                bad_direction="increase",
                expression=lambda service: (
                    "histogram_quantile("
                    "0.95,"
                    "sum by (le) ("
                    "rate(http_request_duration_seconds_bucket{"
                    f'job="{service}"'
                    "}[5m])"
                    ")"
                    ")"
                ),
            ),
            MetricDefinition(
                name="availability",
                display_name="Service availability",
                unit="percent",
                bad_direction="decrease",
                expression=lambda service: (
                    "100 * up{"
                    f'job="{service}"'
                    "}"
                ),
            ),
        ]

    @staticmethod
    def _escape_label(value: str) -> str:
        return (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )


anomaly_detection_service = AnomalyDetectionService()
