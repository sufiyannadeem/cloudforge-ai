from __future__ import annotations

import math
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class PrometheusQueryResult:
    value: list[dict[str, Any]]
    error: str | None = None


@dataclass
class PrometheusRangeResult:
    value: list[dict[str, Any]]
    error: str | None = None


class PrometheusClient:
    """Small dependency-free Prometheus HTTP API client."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("PROMETHEUS_URL")
            or "http://prometheus:9090"
        ).rstrip("/")

        configured_timeout = os.getenv(
            "PROMETHEUS_TIMEOUT_SECONDS",
            "5",
        )

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(configured_timeout)
        )

    def query(self, expression: str) -> PrometheusQueryResult:
        """Execute an instant PromQL query."""

        url = (
            f"{self.base_url}/api/v1/query?"
            f"{urllib.parse.urlencode({'query': expression})}"
        )

        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            return PrometheusQueryResult(
                value=[],
                error=f"Prometheus HTTP {exc.code}: {exc.reason}",
            )

        except urllib.error.URLError as exc:
            return PrometheusQueryResult(
                value=[],
                error=f"Prometheus connection error: {exc.reason}",
            )

        except TimeoutError:
            return PrometheusQueryResult(
                value=[],
                error="Prometheus request timed out",
            )

        except Exception as exc:
            return PrometheusQueryResult(
                value=[],
                error=f"Prometheus query failed: {exc}",
            )

        if payload.get("status") != "success":
            return PrometheusQueryResult(
                value=[],
                error=payload.get("error")
                or "Prometheus returned a non-success response",
            )

        data = payload.get("data", {})
        result = data.get("result", [])

        if not isinstance(result, list):
            return PrometheusQueryResult(
                value=[],
                error="Unexpected Prometheus result format",
            )

        return PrometheusQueryResult(
            value=result,
            error=None,
        )

    def query_range(
        self,
        expression: str,
        start_timestamp: float,
        end_timestamp: float,
        step_seconds: int,
    ) -> PrometheusRangeResult:
        """
        Execute a Prometheus range query.

        Returns the complete matrix returned by Prometheus.
        """

        params = {
            "query": expression,
            "start": str(start_timestamp),
            "end": str(end_timestamp),
            "step": str(step_seconds),
        }

        url = (
            f"{self.base_url}/api/v1/query_range?"
            f"{urllib.parse.urlencode(params)}"
        )

        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            return PrometheusRangeResult(
                value=[],
                error=f"Prometheus HTTP {exc.code}: {exc.reason}",
            )

        except urllib.error.URLError as exc:
            return PrometheusRangeResult(
                value=[],
                error=f"Prometheus connection error: {exc.reason}",
            )

        except TimeoutError:
            return PrometheusRangeResult(
                value=[],
                error="Prometheus range request timed out",
            )

        except Exception as exc:
            return PrometheusRangeResult(
                value=[],
                error=f"Prometheus range query failed: {exc}",
            )

        if payload.get("status") != "success":
            return PrometheusRangeResult(
                value=[],
                error=payload.get("error")
                or "Prometheus returned a non-success response",
            )

        data = payload.get("data", {})
        result = data.get("result", [])

        if not isinstance(result, list):
            return PrometheusRangeResult(
                value=[],
                error="Unexpected Prometheus range result format",
            )

        return PrometheusRangeResult(
            value=result,
            error=None,
        )

    def scalar(
        self,
        expression: str,
    ) -> dict[str, float] | None:
        """
        Execute a PromQL query expected to return one scalar-like
        vector sample.
        """

        result = self.query(expression)

        if result.error or not result.value:
            return None

        value = self._extract_value(result.value[0])

        if value is None:
            return None

        return value

    def service_up(
        self,
        service: str,
    ) -> dict[str, float] | None:
        """Return the Prometheus 'up' state for a service."""

        expression = (
            f'up{{job="{self._escape_label(service)}"}}'
        )

        return self.scalar(expression)

    def collect_operational_context(
        self,
        service: str,
    ) -> dict[str, Any]:
        """
        Collect operational evidence used by incident analysis.

        Missing metrics are represented as None rather than zero.
        This distinction is important because:

            missing metric != measured zero
        """

        service_label = self._escape_label(service)

        queries: dict[str, str] = {
            "service_up": (
                f'up{{job="{service_label}"}}'
            ),

            "request_rate": (
                "sum("
                f'rate(http_requests_total{{service="{service_label}"}}[5m])'
                ")"
            ),

            "error_rate": (
                "100 * ("
                "sum("
                f'rate(http_requests_total{{service="{service_label}",status=~"5.."}}[5m])'
                ") or vector(0)"
                ") / clamp_min(("
                "sum("
                f'rate(http_requests_total{{service="{service_label}"}}[5m])'
                ") or vector(0)"
                "), 1)"
            ),

            "p95_latency": (
                "histogram_quantile("
                "0.95, "
                "sum("
                f'rate(http_request_duration_seconds_bucket{{service="{service_label}"}}[5m])'
                ") by (le)"
                ")"
            ),

            "requests_in_flight": (
                f'http_requests_in_flight{{service="{service_label}"}}'
            ),

            "deployments_in_progress": (
                f'cloudforge_deployments_in_progress{{service="{service_label}"}}'
            ),

            "deployment_failures": (
                "sum("
                f'cloudforge_deployments_total{{service="{service_label}",status="failed"}}'
                ")"
            ),

            "deployment_total": (
                "sum("
                f'cloudforge_deployments_total{{service="{service_label}"}}'
                ")"
            ),
        }

        metrics: dict[str, dict[str, float] | None] = {}
        errors: dict[str, str] = {}

        for name, expression in queries.items():
            result = self.query(expression)

            if result.error:
                errors[name] = result.error
                metrics[name] = None
                continue

            if not result.value:
                metrics[name] = None
                continue

            value = self._extract_value(result.value[0])

            metrics[name] = value

        return {
            "service": service,
            "metrics": metrics,
            "errors": errors,
        }

    @staticmethod
    def _extract_value(
        sample: dict[str, Any],
    ) -> dict[str, float] | None:
        value = sample.get("value")

        if not isinstance(value, list) or len(value) < 2:
            return None

        try:
            timestamp = float(value[0])
            numeric_value = float(value[1])
        except (TypeError, ValueError):
            return None

        return {
            "timestamp": timestamp,
            "value": numeric_value,
        }

    @staticmethod
    def _extract_range_values(
        result: list[dict[str, Any]],
    ) -> list[tuple[float, float]]:
        """
        Extract timestamp/value pairs from a Prometheus matrix.

        Multiple returned series are flattened. The anomaly
        expressions are expected to aggregate to a single series.
        """

        values: list[tuple[float, float]] = []

        for series in result:
            matrix = series.get("values", [])

            if not isinstance(matrix, list):
                continue

            for sample in matrix:
                if not isinstance(sample, list) or len(sample) < 2:
                    continue

                try:
                    timestamp = float(sample[0])
                    value = float(sample[1])
                except (TypeError, ValueError):
                    continue

                if math.isnan(value):
                    continue

                values.append((timestamp, value))

        values.sort(key=lambda item: item[0])

        return values

    def range_values(
        self,
        expression: str,
        start_timestamp: float,
        end_timestamp: float,
        step_seconds: int,
    ) -> tuple[list[tuple[float, float]], str | None]:
        """Execute a range query and return flattened samples."""

        result = self.query_range(
            expression=expression,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            step_seconds=step_seconds,
        )

        if result.error:
            return [], result.error

        return (
            self._extract_range_values(result.value),
            None,
        )

    @staticmethod
    def _escape_label(value: str) -> str:
        return (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
