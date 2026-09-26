from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .ai_provider import AIProvider
from .ai_guardrails import (
    ai_guardrail_validator,
)
from .analyzer import analyze_alert
from .models import (
    AIAnalysis,
    AlertPayload,
    AnalysisConfidence,
)
from .deployment_client import DeploymentClient
from .deployment_correlation import (
    DeploymentCorrelationEngine,
)
from .prometheus_client import PrometheusClient
from .store import IncidentStore


logger = logging.getLogger(__name__)


class IncidentAnalysisService:
    """
    Coordinates:

    Alert
        -> deterministic incident analysis
        -> Prometheus operational evidence
        -> evidence-aware assessment
        -> optional AI provider
        -> persistent AIAnalysis
    """

    def __init__(
        self,
        prometheus_client: PrometheusClient | None = None,
        provider: AIProvider | None = None,
        deployment_client: DeploymentClient | None = None,
        deployment_correlation_engine: (
            DeploymentCorrelationEngine | None
        ) = None,
    ):
        self.prometheus = (
            prometheus_client
            or PrometheusClient()
        )

        self.provider = (
            provider
            or AIProvider()
        )

        self.deployment_client = (
            deployment_client
            or DeploymentClient()
        )

        self.deployment_correlation_engine = (
            deployment_correlation_engine
            or DeploymentCorrelationEngine()
        )

    def analyze_incident(
        self,
        incident_id: str,
        incident_store: IncidentStore,
        use_ai: bool = True,
    ):
        incident = incident_store.get_by_id(incident_id)

        if incident is None:
            return None

        alert = AlertPayload(
            labels=incident.labels,
            annotations=incident.annotations,
            startsAt=(
                incident.created_at.isoformat()
                if incident.created_at
                else datetime.now(timezone.utc).isoformat()
            ),
            endsAt=None,
            status=incident.status,
            generatorURL=None,
        )

        deterministic = analyze_alert(alert)

        operational_context = (
            self.prometheus.collect_operational_context(
                incident.service
            )
        )

        deployment_correlations = (
            self._collect_deployment_correlations(
                incident
            )
        )

        evidence_analysis = (
            self._build_evidence_aware_analysis(
                incident=incident,
                deterministic=deterministic,
                operational_context=operational_context,
                deployment_correlations=(
                    deployment_correlations
                ),
            )
        )

        if not use_ai:
            return incident_store.save_ai_analysis(
                incident.id,
                evidence_analysis,
            )

        if not self.provider.enabled:
            return incident_store.save_ai_analysis(
                incident.id,
                evidence_analysis,
            )

        provider_result = self.provider.analyze(
            system_prompt=self._system_prompt(),
            user_prompt=self._build_user_prompt(
                incident=incident,
                deterministic=evidence_analysis,
                operational_context=operational_context,
            ),
        )

        if provider_result.status == "error":
            logger.warning(
                "AI provider failed for incident %s: %s",
                incident.id,
                provider_result.error,
            )

            return incident_store.save_ai_analysis(
                incident.id,
                evidence_analysis.model_copy(
                    update={
                        "status": "fallback",
                        "provider": provider_result.provider,
                        "model": provider_result.model,
                        "error": provider_result.error,
                    }
                ),
            )

        ai_analysis = self._parse_ai_response(
            provider_result.content or "",
            fallback=evidence_analysis,
            provider=provider_result.provider,
            model=provider_result.model,
        )

        return incident_store.save_ai_analysis(
            incident.id,
            ai_analysis,
        )

    def _collect_deployment_correlations(
        self,
        incident: Any,
    ) -> list[dict[str, object]]:
        """
        Collect deployment evidence near the incident timestamp.

        Deployment proximity is treated as temporal correlation,
        not confirmed causation.
        """

        deployments, error = (
            self.deployment_client.list_deployments(
                limit=100,
                offset=0,
            )
        )

        if error:
            logger.warning(
                "Unable to collect deployment evidence "
                "for incident %s: %s",
                incident.id,
                error,
            )

            return []

        correlations = (
            self.deployment_correlation_engine.correlate(
                incident_time=incident.created_at,
                deployments=deployments,
            )
        )

        return [
            {
                "deployment_id": correlation.deployment_id,
                "environment": correlation.environment,
                "status": correlation.status,
                "image": correlation.image,
                "git_commit_sha": (
                    correlation.git_commit_sha
                ),
                "namespace": correlation.namespace,
                "deployment_created_at": (
                    correlation.deployment_created_at.isoformat()
                ),
                "deployment_updated_at": (
                    correlation.deployment_updated_at.isoformat()
                ),
                "incident_time_difference_seconds": (
                    correlation.incident_time_difference_seconds
                ),
                "correlation_type": (
                    correlation.correlation_type
                ),
                "correlation_strength": (
                    correlation.correlation_strength
                ),
                "explanation": (
                    correlation.explanation
                ),
            }
            for correlation in correlations
        ]

    def _build_evidence_aware_analysis(
        self,
        incident: Any,
        deterministic: Any,
        operational_context: dict[str, Any],
        deployment_correlations: list[
            dict[str, object]
        ],
    ) -> AIAnalysis:
        """
        Compare the alert that created the incident with current
        Prometheus telemetry.

        The analyzer must distinguish:

        1. Alert supported by current evidence.
        2. Alert not currently observed.
        3. Insufficient evidence.
        4. Service currently unhealthy.
        """

        metrics = operational_context.get("metrics", {})
        errors = operational_context.get("errors", {})

        evidence = {
            "service_up": self._metric_value(
                metrics,
                "service_up",
            ),
            "request_rate": self._metric_value(
                metrics,
                "request_rate",
            ),
            "error_rate": self._metric_value(
                metrics,
                "error_rate",
            ),
            "p95_latency_seconds": self._metric_value(
                metrics,
                "p95_latency",
            ),
            "requests_in_flight": self._metric_value(
                metrics,
                "requests_in_flight",
            ),
            "deployments_in_progress": self._metric_value(
                metrics,
                "deployments_in_progress",
            ),
            "deployment_failures": self._metric_value(
                metrics,
                "deployment_failures",
            ),
            "deployment_total": self._metric_value(
                metrics,
                "deployment_total",
            ),
        }

        findings: list[str] = []

        alert_name = incident.alert_name

        # ---------------------------------------------------------
        # Deployment correlation
        # ---------------------------------------------------------

        if deployment_correlations:
            strongest = (
                deployment_correlations[0]
            )

            findings.append(
                f"{len(deployment_correlations)} "
                "deployment(s) were detected within "
                "the incident correlation window."
            )

            findings.append(
                "The closest deployment was "
                f"{strongest['incident_time_difference_seconds']:.1f} "
                "seconds from the incident timestamp."
            )

            findings.append(
                "Deployment timing is treated as temporal "
                "correlation and does not establish causation."
            )
        else:
            findings.append(
                "No deployment was detected within the "
                "incident correlation window."
            )

        service_up = evidence["service_up"]
        request_rate = evidence["request_rate"]
        error_rate = evidence["error_rate"]
        p95_latency = evidence["p95_latency_seconds"]
        requests_in_flight = evidence["requests_in_flight"]
        deployments_in_progress = evidence["deployments_in_progress"]
        deployment_failures = evidence["deployment_failures"]

        # ---------------------------------------------------------
        # Service availability
        # ---------------------------------------------------------

        if service_up is None:
            findings.append(
                "Current service availability could not be determined "
                "from Prometheus."
            )
        elif service_up < 1:
            findings.append(
                "Prometheus currently reports the service as unavailable."
            )
        else:
            findings.append(
                "Prometheus currently reports the service as healthy."
            )

        # ---------------------------------------------------------
        # Request traffic
        # ---------------------------------------------------------

        if request_rate is None:
            findings.append(
                "Current request rate could not be determined."
            )
        elif request_rate <= 0:
            findings.append(
                "No current request traffic was observed."
            )
        else:
            findings.append(
                f"Current request rate is approximately "
                f"{request_rate:.4f} requests/second."
            )

        # ---------------------------------------------------------
        # Error rate
        # ---------------------------------------------------------

        if error_rate is None:
            findings.append(
                "Current HTTP error rate could not be determined."
            )
        elif error_rate <= 0:
            findings.append(
                "Current HTTP 5xx error rate is 0%."
            )
        else:
            findings.append(
                f"Current HTTP 5xx error rate is approximately "
                f"{error_rate:.2f}%."
            )

        # ---------------------------------------------------------
        # Latency
        # ---------------------------------------------------------

        if p95_latency is None:
            findings.append(
                "Current P95 latency could not be determined."
            )
        else:
            p95_ms = p95_latency * 1000

            findings.append(
                f"Current P95 request latency is approximately "
                f"{p95_ms:.2f} ms."
            )

        # ---------------------------------------------------------
        # Request concurrency
        # ---------------------------------------------------------

        if requests_in_flight is not None:
            findings.append(
                f"Current requests in flight: "
                f"{requests_in_flight:.0f}."
            )

        # ---------------------------------------------------------
        # Deployment state
        # ---------------------------------------------------------

        if deployments_in_progress is not None:
            if deployments_in_progress > 0:
                findings.append(
                    f"{deployments_in_progress:.0f} deployment(s) "
                    "are currently in progress."
                )
            else:
                findings.append(
                    "No deployment is currently in progress."
                )

        if deployment_failures is not None:
            if deployment_failures > 0:
                findings.append(
                    f"Prometheus reports {deployment_failures:.0f} "
                    "failed deployment(s) in the observed period."
                )
            else:
                findings.append(
                    "No failed deployments are currently reported."
                )

        # ---------------------------------------------------------
        # Evaluate the alert against live evidence.
        # ---------------------------------------------------------

        assessment = "insufficient_evidence"
        confidence = AnalysisConfidence.LOW

        probable_cause = deterministic.probable_cause

        if alert_name == "DeploymentServiceDown":
            if service_up is not None:
                if service_up < 1:
                    assessment = "alert_supported"
                    confidence = AnalysisConfidence.HIGH

                    probable_cause = (
                        "Prometheus currently reports deployment-service "
                        "as unavailable."
                    )

                else:
                    assessment = "alert_not_currently_observed"
                    confidence = AnalysisConfidence.HIGH

                    probable_cause = (
                        "The alert indicates a deployment-service outage, "
                        "but current Prometheus telemetry reports the "
                        "service as healthy."
                    )

        elif alert_name == "DeploymentServiceHighErrorRate":
            if error_rate is not None:
                if error_rate > 5:
                    assessment = "alert_supported"
                    confidence = AnalysisConfidence.HIGH

                    probable_cause = (
                        "Current Prometheus telemetry shows an HTTP 5xx "
                        f"error rate of approximately {error_rate:.2f}%."
                    )
                else:
                    assessment = "alert_not_currently_observed"
                    confidence = AnalysisConfidence.HIGH

                    probable_cause = (
                        "The alert indicates elevated HTTP error rate, "
                        "but current Prometheus telemetry reports an "
                        f"error rate of {error_rate:.2f}%."
                    )

        elif alert_name == "DeploymentServiceHighP95Latency":
            if p95_latency is not None:
                p95_ms = p95_latency * 1000

                if p95_latency > 1:
                    assessment = "alert_supported"
                    confidence = AnalysisConfidence.HIGH

                    probable_cause = (
                        "Current Prometheus telemetry shows elevated "
                        f"P95 request latency of approximately "
                        f"{p95_ms:.2f} ms."
                    )
                else:
                    assessment = "alert_not_currently_observed"
                    confidence = AnalysisConfidence.HIGH

                    probable_cause = (
                        "The alert indicates elevated P95 latency, "
                        "but current Prometheus telemetry reports "
                        f"P95 latency of approximately {p95_ms:.2f} ms."
                    )

        else:
            # Generic alert handling.
            available_metrics = [
                value for value in evidence.values()
                if value is not None
            ]

            if available_metrics:
                assessment = "evidence_available"
                confidence = AnalysisConfidence.MEDIUM

                probable_cause = (
                    "Current operational evidence is available, but "
                    "CloudForge does not yet have a specialized "
                    f"evidence rule for {alert_name}."
                )

        # ---------------------------------------------------------
        # Add evidence conflict/support language.
        # ---------------------------------------------------------

        if assessment == "alert_not_currently_observed":
            findings.insert(
                0,
                "Current telemetry does not support the alert condition "
                "at analysis time; the alert may represent a recovered "
                "or historical condition.",
            )

        elif assessment == "alert_supported":
            findings.insert(
                0,
                "Current telemetry supports the condition represented "
                "by the incoming alert.",
            )

        elif assessment == "insufficient_evidence":
            findings.insert(
                0,
                "Available telemetry is insufficient to determine whether "
                "the alert condition is currently present.",
            )

        # ---------------------------------------------------------
        # Recommended actions
        # ---------------------------------------------------------

        recommended_actions = list(
            deterministic.recommended_actions
        )

        if assessment == "alert_not_currently_observed":
            recommended_actions = [
                "Verify whether the alert condition has recovered.",
                "Review the incident timeline for when the condition occurred.",
                "Compare historical alert timestamps with Prometheus telemetry.",
                "Check recent deployments and configuration changes.",
            ]

        elif assessment == "alert_supported":
            recommended_actions = [
                "Inspect deployment-service application logs.",
                "Correlate the alert with current Prometheus metrics.",
                "Check recent deployments and configuration changes.",
                "Inspect downstream dependencies and database health.",
            ]

        elif assessment == "insufficient_evidence":
            recommended_actions = [
                "Verify Prometheus target health.",
                "Inspect service logs.",
                "Check whether the required metrics are being exported.",
                "Review the incident timeline and alert annotations.",
            ]

        summary = (
            f"Evidence-aware analysis for {incident.alert_name} "
            f"on {incident.service}: {assessment}."
        )

        return AIAnalysis(
            status="deterministic",
            provider="deterministic",
            model=None,
            summary=summary,
            probable_cause=probable_cause,
            root_cause_hints=list(
                deterministic.root_cause_hints
            ),
            recommended_actions=recommended_actions,
            confidence=confidence,
            assessment=assessment,
            evidence=evidence,
            evidence_findings=findings,
            deployment_correlations=(
                deployment_correlations
            ),
            generated_at=datetime.now(timezone.utc),
            error=None,
        )

    @staticmethod
    def _metric_value(
        metrics: dict[str, Any],
        name: str,
    ) -> float | None:
        value = metrics.get(name)

        if value is None:
            return None

        if isinstance(value, dict):
            value = value.get("value")

        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_user_prompt(
        self,
        incident: Any,
        deterministic: AIAnalysis,
        operational_context: dict[str, Any],
    ) -> str:
        payload = {
            "prometheus_context": operational_context,
            "deployment_correlations": (
                deterministic.deployment_correlations
            ),
            "deterministic_analysis": (
                deterministic.model_dump(
                    mode="json"
                )
            ),
            "operational_context": operational_context,
        }

        return (
            "Analyze this production incident using only the supplied "
            "incident information and operational evidence.\n\n"
            "Do not invent metrics, logs, causes, or events.\n"
            "Clearly distinguish current evidence from historical "
            "alert information.\n"
            "If current telemetry conflicts with the alert, explicitly "
            "state that the condition is not currently observed.\n"
            "Treat deployment proximity as temporal correlation only; "
            "do not claim that a deployment caused the incident unless "
            "the supplied evidence directly establishes causation.\n"
            "Distinguish observed facts from hypotheses.\n\n"
            "Return valid JSON matching the AIAnalysis structure.\n\n"
            + json.dumps(payload, indent=2, default=str)
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are CloudForge Incident Intelligence. "
            "Analyze production incidents conservatively. "
            "Use only supplied evidence. "
            "Never invent observations. "
            "Never claim a root cause is confirmed unless the supplied "
            "evidence supports that conclusion. "
            "Treat deployment proximity as temporal correlation only. "
            "Do not claim deployment causation without supporting evidence. "
            "Distinguish historical alerts from current service state."
        )

    def _parse_ai_response(
        self,
        content: str,
        fallback: AIAnalysis,
        provider: str = "ai",
        model: str | None = None,
    ) -> AIAnalysis:
        """
        Validate untrusted AI output before persistence.

        Deterministic evidence remains authoritative.
        Invalid AI output falls back to deterministic analysis.
        """

        validation = ai_guardrail_validator.validate(
            content=content,
            fallback=fallback,
        )

        if validation.valid and validation.analysis:
            return validation.analysis

        error = (
            validation.error
            or "AI response failed validation."
        )

        logger.warning(
            "AI guardrail validation failed: %s",
            error,
        )

        return fallback.model_copy(
            update={
                "status": "fallback",
                "provider": provider,
                "model": model,
                "error": (
                    "AI response rejected by guardrails: "
                    f"{error}"
                ),
            }
        )


incident_analysis_service = IncidentAnalysisService()
