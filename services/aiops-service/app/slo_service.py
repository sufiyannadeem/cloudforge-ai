from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from .prometheus_client import PrometheusClient
from .telemetry_queries import api_requests, positive_ratio, with_counter_samples
from .slo_models import (
    SLODefinition,
    SLOResult,
    SLOStatus,
    SLOSummary,
    SLOType,
)


DEFAULT_SERVICE = "deployment-service"
DEFAULT_WINDOW = os.getenv("SLO_WINDOW", "7d")
SCRAPE_INTERVAL_SECONDS = float(os.getenv("SLO_SCRAPE_INTERVAL_SECONDS", "15"))
_DURATION_UNITS = {"y": 31536000, "w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1, "ms": 0.001}


def window_seconds(window: str) -> float:
    parts = re.findall(r"([0-9]+)(ms|[ywdhms])", window)
    if not parts or "".join(value + unit for value, unit in parts) != window:
        raise ValueError("Invalid SLO window")
    return sum(int(value) * _DURATION_UNITS[unit] for value, unit in parts)

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
                name="Latency Compliance",
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
        elif insufficient_count > 0:
            overall_status = SLOStatus.INSUFFICIENT_DATA
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

        up = f'up{{job="{self._escape_label(service)}"}}'
        expression = f"avg(avg_over_time({up}[{definition.window}]))"
        return self._evaluate_ratio(definition, self._with_window_evidence(definition, expression))

    def _with_window_evidence(
        self,
        definition: SLODefinition,
        expression: str,
        selector: str | None = None,
    ) -> str:
        up = f'up{{job="{self._escape_label(definition.service)}"}}'
        window = definition.window
        minimum = max(2, window_seconds(window) * 0.9 / SCRAPE_INTERVAL_SECONDS)
        guarded = (
            f"({expression}) "
            f"and on() (min(count_over_time({up}[{window}])) >= {minimum:g}) "
            f"and on() (max(time() - timestamp({up})) <= {SCRAPE_INTERVAL_SECONDS * 3:g})"
        )
        if selector is not None:
            # New status/route series need two samples, while at least one
            # measured API counter must cover the reporting window.
            guarded += (
                f" and on() (max(count_over_time({selector}[{window}])) >= {minimum:g})"
                f" and on() (max(time() - timestamp({selector})) <= {SCRAPE_INTERVAL_SECONDS * 3:g})"
            )
        return guarded

    def _evaluate_error_rate(self, service: str) -> SLOResult:
        definition = self.definitions(service)[1]
        labels = api_requests(self._escape_label(service))
        total = f"sum(increase(http_requests_total{{{labels}}}[{definition.window}]))"
        errors = f'sum(increase(http_requests_total{{{labels},status=~"5.."}}[{definition.window}]))'
        ratio = positive_ratio(errors, total, missing_numerator_is_zero=True)
        expression = with_counter_samples(f"1 - {ratio}", f"http_requests_total{{{labels}}}", definition.window)
        return self._evaluate_ratio(
            definition,
            self._with_window_evidence(definition, expression, f"http_requests_total{{{labels}}}"),
        )

    def _evaluate_latency(self, service: str) -> SLOResult:
        definition = self.definitions(service)[2]
        labels = api_requests(self._escape_label(service))
        threshold = f"{LATENCY_THRESHOLD_MS / 1000:g}"
        good = f'sum(increase(http_request_duration_seconds_bucket{{{labels},le="{threshold}"}}[{definition.window}]))'
        total = f"sum(increase(http_request_duration_seconds_count{{{labels}}}[{definition.window}]))"
        expression = with_counter_samples(
            positive_ratio(good, total), f"http_request_duration_seconds_count{{{labels}}}", definition.window,
        )
        return self._evaluate_ratio(
            definition,
            self._with_window_evidence(
                definition, expression, f"http_request_duration_seconds_count{{{labels}}}",
            ),
        )

    def _evaluate_ratio(self, definition: SLODefinition, expression: str) -> SLOResult:
        sample = self.prometheus.scalar(expression)
        if sample is None or not 0.0 <= sample["value"] <= 1.0:
            return self._insufficient(definition)
        return self._build_result(definition, observed_value=sample["value"], compliance=sample["value"])

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

            budget_consumed = burn_rate

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
