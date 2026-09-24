from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .prometheus_client import PrometheusClient
from .slo_models import (
    SLODefinition,
    SLOResult,
    SLOStatus,
    SLOSummary,
    SLOType,
)


DEFAULT_SERVICE = "deployment-service"
DEFAULT_WINDOW = os.getenv("SLO_WINDOW", "7d")

AVAILABILITY_TARGET = float(
    os.getenv("SLO_AVAILABILITY_TARGET", "0.999")
)

ERROR_RATE_TARGET = float(
    os.getenv("SLO_ERROR_RATE_TARGET", "0.99")
)

LATENCY_TARGET = float(
    os.getenv("SLO_LATENCY_TARGET", "0.95")
)

LATENCY_THRESHOLD_MS = float(
    os.getenv("SLO_LATENCY_THRESHOLD_MS", "500")
)


class SLOService:
    """
    Calculates SLO compliance and error-budget state from Prometheus.

    Important:
    - This service does not invent historical data.
    - Missing Prometheus data produces insufficient_data.
    - The configured SLO window is bounded by Prometheus retention.
    """

    def __init__(
        self,
        prometheus_client: PrometheusClient | None = None,
    ) -> None:
        self.prometheus = prometheus_client or PrometheusClient()

    def definitions(
        self,
        service: str = DEFAULT_SERVICE,
    ) -> list[SLODefinition]:
        return [
            SLODefinition(
                name="Availability",
                description=(
                    "Percentage of the SLO window during which "
                    "the deployment service was available."
                ),
                service=service,
                type=SLOType.AVAILABILITY,
                target=AVAILABILITY_TARGET,
                window=DEFAULT_WINDOW,
            ),
            SLODefinition(
                name="Request Success",
                description=(
                    "Percentage of HTTP requests that did not "
                    "return a server-side 5xx response."
                ),
                service=service,
                type=SLOType.ERROR_RATE,
                target=ERROR_RATE_TARGET,
                window=DEFAULT_WINDOW,
            ),
            SLODefinition(
                name="P95 Latency",
                description=(
                    "Percentage of requests completing within "
                    "the configured latency threshold."
                ),
                service=service,
                type=SLOType.LATENCY,
                target=LATENCY_TARGET,
                window=DEFAULT_WINDOW,
                latency_threshold_ms=LATENCY_THRESHOLD_MS,
            ),
        ]

    def evaluate(
        self,
        service: str = DEFAULT_SERVICE,
    ) -> SLOSummary:
        results = [
            self._evaluate_availability(service),
            self._evaluate_error_rate(service),
            self._evaluate_latency(service),
        ]

        healthy_count = sum(
            result.status == SLOStatus.HEALTHY
            for result in results
        )

        at_risk_count = sum(
            result.status == SLOStatus.AT_RISK
            for result in results
        )

        breached_count = sum(
            result.status == SLOStatus.BREACHED
            for result in results
        )

        insufficient_count = sum(
            result.status == SLOStatus.INSUFFICIENT_DATA
            for result in results
        )

        if breached_count > 0:
            overall_status = SLOStatus.BREACHED
        elif at_risk_count > 0:
            overall_status = SLOStatus.AT_RISK
        elif insufficient_count == len(results):
            overall_status = SLOStatus.INSUFFICIENT_DATA
        elif insufficient_count > 0:
            overall_status = SLOStatus.AT_RISK
        else:
            overall_status = SLOStatus.HEALTHY

        return SLOSummary(
            service=service,
            window=DEFAULT_WINDOW,
            overall_status=overall_status,
            slo_count=len(results),
            healthy_count=healthy_count,
            at_risk_count=at_risk_count,
            breached_count=breached_count,
            insufficient_data_count=insufficient_count,
            slos=results,
            generated_at=datetime.now(timezone.utc),
        )

    def _evaluate_availability(
        self,
        service: str,
    ) -> SLOResult:
        definition = self.definitions(service)[0]

        expression = (
            f'avg_over_time(up{{job="{self._escape_label(service)}"}}'
            f'[{DEFAULT_WINDOW}])'
        )

        sample = self.prometheus.scalar(expression)

        if sample is None:
            return self._insufficient(definition)

        availability = self._clamp(
            sample["value"],
            0.0,
            1.0,
        )

        return self._build_result(
            definition=definition,
            observed_value=availability,
            compliance=availability,
        )

    def _evaluate_error_rate(
        self,
        service: str,
    ) -> SLOResult:
        definition = self.definitions(service)[1]

        service_label = self._escape_label(service)

        total_expression = (
            f'sum(increase(http_requests_total'
            f'{{job="{service_label}"}}[{DEFAULT_WINDOW}]))'
        )

        error_expression = (
            f'sum(increase(http_requests_total'
            f'{{job="{service_label}",status=~"5.."}}'
            f'[{DEFAULT_WINDOW}]))'
        )

        total = self.prometheus.scalar(total_expression)
        errors = self.prometheus.scalar(error_expression)

        if total is None or total["value"] <= 0:
            return self._insufficient(definition)

        error_count = (
            errors["value"]
            if errors is not None
            else 0.0
        )

        success_ratio = self._clamp(
            1.0 - (error_count / total["value"]),
            0.0,
            1.0,
        )

        return self._build_result(
            definition=definition,
            observed_value=success_ratio,
            compliance=success_ratio,
        )

    def _evaluate_latency(
        self,
        service: str,
    ) -> SLOResult:
        definition = self.definitions(service)[2]

        service_label = self._escape_label(service)

        threshold_seconds = (
            LATENCY_THRESHOLD_MS / 1000.0
        )

        bucket_expression = (
            f'sum(increase(http_request_duration_seconds_bucket'
            f'{{job="{service_label}",'
            f'le="{threshold_seconds}"}}'
            f'[{DEFAULT_WINDOW}]))'
        )

        total_expression = (
            f'sum(increase(http_request_duration_seconds_count'
            f'{{job="{service_label}"}}'
            f'[{DEFAULT_WINDOW}]))'
        )

        good = self.prometheus.scalar(bucket_expression)
        total = self.prometheus.scalar(total_expression)

        if good is None or total is None or total["value"] <= 0:
            return self._insufficient(definition)

        good_requests = max(
            0.0,
            min(good["value"], total["value"]),
        )

        compliance = self._clamp(
            good_requests / total["value"],
            0.0,
            1.0,
        )

        return self._build_result(
            definition=definition,
            observed_value=compliance,
            compliance=compliance,
        )

    def _build_result(
        self,
        definition: SLODefinition,
        observed_value: float,
        compliance: float,
    ) -> SLOResult:
        target = definition.target

        allowed_bad_fraction = 1.0 - target
        observed_bad_fraction = 1.0 - compliance

        if allowed_bad_fraction <= 0:
            burn_rate = None
            budget_consumed = None
            budget_remaining = None
        else:
            burn_rate = (
                observed_bad_fraction
                / allowed_bad_fraction
            )

            budget_consumed = self._clamp(
                burn_rate,
                0.0,
                1.0,
            )

            budget_remaining = self._clamp(
                1.0 - budget_consumed,
                0.0,
                1.0,
            )

        status = self._determine_status(
            compliance=compliance,
            target=target,
            burn_rate=burn_rate,
        )

        return SLOResult(
            name=definition.name,
            description=definition.description,
            service=definition.service,
            type=definition.type,
            target=target,
            window=definition.window,
            observed_value=observed_value,
            compliance=compliance,
            error_budget_total=allowed_bad_fraction,
            error_budget_consumed=budget_consumed,
            error_budget_remaining=budget_remaining,
            burn_rate=burn_rate,
            status=status,
            sufficient_data=True,
            latency_threshold_ms=definition.latency_threshold_ms,
            observed_at=datetime.now(timezone.utc),
        )

    def _insufficient(
        self,
        definition: SLODefinition,
    ) -> SLOResult:
        return SLOResult(
            name=definition.name,
            description=definition.description,
            service=definition.service,
            type=definition.type,
            target=definition.target,
            window=definition.window,
            observed_value=None,
            compliance=None,
            error_budget_total=1.0 - definition.target,
            error_budget_consumed=None,
            error_budget_remaining=None,
            burn_rate=None,
            status=SLOStatus.INSUFFICIENT_DATA,
            sufficient_data=False,
            latency_threshold_ms=definition.latency_threshold_ms,
            observed_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _determine_status(
        compliance: float,
        target: float,
        burn_rate: float | None,
    ) -> SLOStatus:
        if compliance < target:
            return SLOStatus.BREACHED

        if burn_rate is not None and burn_rate >= 1.0:
            return SLOStatus.AT_RISK

        if burn_rate is not None and burn_rate >= 0.5:
            return SLOStatus.AT_RISK

        return SLOStatus.HEALTHY

    @staticmethod
    def _clamp(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        return max(minimum, min(maximum, value))

    @staticmethod
    def _escape_label(value: str) -> str:
        return (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )


slo_service = SLOService()
