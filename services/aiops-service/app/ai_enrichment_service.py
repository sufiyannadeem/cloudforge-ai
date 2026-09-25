from __future__ import annotations

import json
import logging
from typing import Any

from .ai_enrichment_guardrails import (
    AIEnrichmentGuardrailError,
    ai_enrichment_guardrails,
)
from .ai_enrichment_models import (
    AIEnrichment,
    AIEnrichmentResponse,
    EnrichmentConfidence,
    EnrichmentStatus,
    EvidencePack,
)
from .ai_provider import AIProvider
from .anomaly_service import anomaly_detection_service
from .store import incident_store
from .slo_service import slo_service


logger = logging.getLogger(__name__)


class AIEnrichmentService:
    """
    Produces evidence-grounded AI enrichment.

    Deterministic evidence is collected first.

    AI is an interpretation layer only.
    """

    def __init__(
        self,
        provider: AIProvider | None = None,
    ) -> None:
        self.provider = provider or AIProvider()

    def enrich(
        self,
        incident_id: str,
    ) -> AIEnrichmentResponse | None:
        incident = incident_store.get_by_id(
            incident_id
        )

        if incident is None:
            return None

        evidence = self._build_evidence_pack(
            incident
        )

        fallback = self._build_fallback(
            evidence
        )

        if not self.provider.enabled:
            fallback.status = (
                EnrichmentStatus.DISABLED
            )

            return AIEnrichmentResponse(
                incident_id=incident_id,
                enrichment=fallback,
                evidence=evidence,
            )

        try:
            provider_result = self.provider.analyze(
                system_prompt=self._system_prompt(),
                user_prompt=self._build_prompt(
                    evidence
                ),
            )

        except Exception as exc:
            logger.exception(
                "AI enrichment provider exception "
                "for incident %s",
                incident_id,
            )

            fallback.error = str(exc)

            fallback.guardrail_warnings.append(
                "AI provider raised an unexpected exception."
            )

            return AIEnrichmentResponse(
                incident_id=incident_id,
                enrichment=fallback,
                evidence=evidence,
            )

        if provider_result.status != "success":
            fallback.error = (
                provider_result.error
            )

            fallback.guardrail_warnings.append(
                "AI provider failed; deterministic "
                "fallback was used."
            )

            return AIEnrichmentResponse(
                incident_id=incident_id,
                enrichment=fallback,
                evidence=evidence,
            )

        try:
            enrichment = (
                self._parse_provider_response(
                    provider_result.content or "",
                    provider=provider_result.provider,
                    model=provider_result.model,
                    evidence=evidence,
                )
            )

            ai_enrichment_guardrails.validate(
                enrichment,
                evidence,
            )

        except (
            ValueError,
            TypeError,
            AIEnrichmentGuardrailError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning(
                "AI enrichment rejected for %s: %s",
                incident_id,
                exc,
            )

            fallback.guardrail_warnings.append(
                f"AI response rejected: {exc}"
            )

            return AIEnrichmentResponse(
                incident_id=incident_id,
                enrichment=fallback,
                evidence=evidence,
            )

        return AIEnrichmentResponse(
            incident_id=incident_id,
            enrichment=enrichment,
            evidence=evidence,
        )

    def _build_evidence_pack(
        self,
        incident: Any,
    ) -> EvidencePack:
        anomaly = (
            anomaly_detection_service.evaluate(
                service=incident.service,
                window_minutes=60,
                step_seconds=60,
            )
        )

        slo = slo_service.evaluate(
            service=incident.service
        )

        operational_metrics: dict[
            str,
            float | int | None,
        ] = {}

        deterministic_assessment = None
        evidence_findings: list[str] = []
        deployment_correlations: list[
            dict[str, object]
        ] = []

        if incident.ai_analysis:
            operational_metrics.update(
                incident.ai_analysis.evidence
            )

            deterministic_assessment = (
                incident.ai_analysis.assessment
            )

            evidence_findings.extend(
                incident.ai_analysis.evidence_findings
            )

            deployment_correlations.extend(
                incident.ai_analysis.deployment_correlations
            )

        return EvidencePack(
            incident_id=incident.id,
            service=incident.service,
            alert_name=incident.alert_name,
            incident_summary=incident.summary,
            deterministic_assessment=(
                deterministic_assessment
            ),
            evidence_findings=evidence_findings,
            operational_metrics=operational_metrics,
            anomaly_classification=(
                anomaly.overall_classification.value
            ),
            anomaly_metrics=[
                metric.model_dump(mode="json")
                for metric in anomaly.metrics
            ],
            slo_classification=(
                self._slo_classification(slo)
            ),
            slo_results=[
                result.model_dump(mode="json")
                for result in slo.slos
            ],
            deployment_correlations=(
                deployment_correlations
            ),
        )

    @staticmethod
    def _slo_classification(
        slo: Any,
    ) -> str:
        statuses = [
            result.status.value
            for result in slo.slos
        ]

        if "breached" in statuses:
            return "breached"

        if "at_risk" in statuses:
            return "at_risk"

        if statuses and all(
            status == "healthy"
            for status in statuses
        ):
            return "healthy"

        return "insufficient_data"

    def _build_fallback(
        self,
        evidence: EvidencePack,
    ) -> AIEnrichment:
        signals: list[str] = []

        if evidence.anomaly_classification in {
            "anomaly",
            "critical",
        }:
            signals.append(
                "Anomaly detection reported "
                f"{evidence.anomaly_classification} behavior."
            )

        if evidence.slo_classification in {
            "breached",
            "at_risk",
        }:
            signals.append(
                "SLO evaluation reported "
                f"{evidence.slo_classification}."
            )

        if evidence.deployment_correlations:
            signals.append(
                "A deployment was temporally correlated "
                "with the incident."
            )

        return AIEnrichment(
            status=EnrichmentStatus.FALLBACK,
            provider="deterministic",
            model=None,
            summary=(
                "Deterministic evidence was collected, "
                "but AI enrichment was not available "
                "or was rejected."
            ),
            probable_cause=(
                evidence.deterministic_assessment
                or (
                    "No evidence-backed probable cause "
                    "was established."
                )
            ),
            contributing_signals=signals,
            investigation_steps=[
                "Review the deterministic incident evidence.",
                "Review current anomaly classifications.",
                "Review SLO and error-budget state.",
                "Inspect correlated deployments before "
                "taking action.",
            ],
            confidence=EnrichmentConfidence.LOW,
            evidence_used=(
                evidence.evidence_findings[:4]
            ),
        )

    @staticmethod
    def _system_prompt() -> str:
        return """
You are CloudForge AI's incident-enrichment assistant.

You are an evidence interpreter, not an autonomous operator.

Rules:
1. Use only supplied deterministic evidence.
2. Never invent telemetry.
3. Never modify authoritative evidence.
4. Never claim confirmed causality from temporal correlation.
5. Use cautious language when evidence is incomplete.
6. Do not recommend destructive or irreversible actions.
7. Investigation steps must be operator-led and reversible.
8. Return JSON only.
"""

    @staticmethod
    def _build_prompt(
        evidence: EvidencePack,
    ) -> str:
        """
        Preserve the existing AI provider contract.

        The existing MockAIProvider expects:
          deterministic_analysis
          operational_context
          deployment_correlations
        """

        deterministic_assessment = (
            evidence.deterministic_assessment
            or "evidence_available"
        )

        probable_cause = (
            "The supplied evidence supports the observed "
            "incident condition, but it does not establish "
            "causality."
        )

        if deterministic_assessment == "alert_not_currently_observed":
            probable_cause = (
                "The alert condition is not currently "
                "observed in the available live telemetry."
            )
        elif deterministic_assessment == "insufficient_evidence":
            probable_cause = (
                "Available telemetry is insufficient to "
                "determine a probable cause."
            )

        deterministic_analysis = {
            "summary": evidence.incident_summary,
            "probable_cause": probable_cause,
            "root_cause_hints": [],
            "recommended_actions": [
                "Review the supplied operational evidence.",
                "Review correlated deployment activity.",
            ],
            "confidence": "medium",
            "assessment": deterministic_assessment,
            "evidence": evidence.operational_metrics,
            "evidence_findings": evidence.evidence_findings,
        }

        operational_context = {
            "service": evidence.service,
            "metrics": (
                evidence.operational_metrics
            ),
            "anomaly_classification": (
                evidence.anomaly_classification
            ),
            "anomaly_metrics": (
                evidence.anomaly_metrics
            ),
            "slo_classification": (
                evidence.slo_classification
            ),
            "slo_results": (
                evidence.slo_results
            ),
        }

        payload = {
            "incident_id": evidence.incident_id,
            "service": evidence.service,
            "alert_name": evidence.alert_name,
            "deterministic_analysis": (
                deterministic_analysis
            ),
            "operational_context": (
                operational_context
            ),
            "deployment_correlations": (
                evidence.deployment_correlations
            ),
        }

        return (
            "Use only the evidence in this JSON payload.\n"
            "Do not invent telemetry or causality.\n"
            "Return a JSON object compatible with the "
            "CloudForge AI enrichment schema.\n\n"
            f"{json.dumps(payload, indent=2, default=str)}"
        )

    @staticmethod
    def _parse_provider_response(
        content: str,
        *,
        provider: str,
        model: str | None,
        evidence: EvidencePack,
    ) -> AIEnrichment:
        """
        Parse and validate the raw provider response before AI output
        is converted into the public AIEnrichment model.

        Deterministic telemetry remains authoritative. AI-provided
        evidence, assessment, and deployment correlations must match
        the evidence pack exactly.
        """
        cleaned = content.strip()

        if not cleaned:
            raise ValueError(
                "AI provider returned an empty response."
            )

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()

            if lines:
                lines = lines[1:]

            if (
                lines
                and lines[-1].strip() == "```"
            ):
                lines = lines[:-1]

            cleaned = "\n".join(lines).strip()

        payload = json.loads(cleaned)

        if not isinstance(payload, dict):
            raise ValueError(
                "AI response must be a JSON object."
            )

        AIEnrichmentService._validate_provider_assessment(
            payload,
            evidence,
        )

        AIEnrichmentService._validate_provider_evidence(
            payload,
            evidence,
        )

        AIEnrichmentService._validate_provider_deployment_correlations(
            payload,
            evidence,
        )

        confidence = payload.get(
            "confidence",
            "medium",
        )

        try:
            confidence_enum = EnrichmentConfidence(
                confidence
            )
        except ValueError as exc:
            raise ValueError(
                "AI response contains an unsupported confidence value."
            ) from exc

        contributing_signals = payload.get(
            "contributing_signals",
            payload.get("root_cause_hints", []),
        )

        investigation_steps = payload.get(
            "investigation_steps",
            payload.get("recommended_actions", []),
        )

        evidence_used = payload.get(
            "evidence_used",
            evidence.evidence_findings,
        )

        if not isinstance(contributing_signals, list):
            raise ValueError(
                "AI contributing_signals must be a list."
            )

        if not isinstance(investigation_steps, list):
            raise ValueError(
                "AI investigation_steps must be a list."
            )

        if not isinstance(evidence_used, list):
            raise ValueError(
                "AI evidence_used must be a list."
            )

        return AIEnrichment(
            status=EnrichmentStatus.AI,
            provider=provider,
            model=model,
            summary=str(
                payload.get(
                    "summary",
                    "AI enrichment generated.",
                )
            ),
            probable_cause=str(
                payload.get(
                    "probable_cause",
                    (
                        "The available evidence does not "
                        "establish a confirmed root cause."
                    ),
                )
            ),
            contributing_signals=[
                str(item)
                for item in contributing_signals
            ],
            investigation_steps=[
                str(item)
                for item in investigation_steps
            ],
            confidence=confidence_enum,
            causality=str(
                payload.get(
                    "causality",
                    (
                        "Temporal or contextual correlation "
                        "only; causality is not established."
                    ),
                )
            ),
            evidence_used=[
                str(item)
                for item in evidence_used
            ],
        )

    @staticmethod
    def _validate_provider_assessment(
        payload: dict[str, Any],
        evidence: EvidencePack,
    ) -> None:
        allowed = {
            "alert_supported",
            "alert_not_currently_observed",
            "evidence_available",
            "insufficient_evidence",
        }

        assessment = payload.get("assessment")

        if assessment is None:
            raise ValueError(
                "AI response is missing the required assessment."
            )

        if assessment not in allowed:
            raise ValueError(
                f"AI response contains unsupported assessment: "
                f"{assessment!r}."
            )

        has_incident_evidence = bool(
            evidence.deterministic_assessment
            or evidence.evidence_findings
            or evidence.operational_metrics
            or evidence.anomaly_metrics
            or evidence.slo_results
            or evidence.deployment_correlations
        )

        if not has_incident_evidence:
            if assessment != "insufficient_evidence":
                raise ValueError(
                    "AI assessment contradicts the absence of "
                    "deterministic incident evidence."
                )
            return

        if (
            evidence.anomaly_classification in {"anomaly", "critical"}
            or evidence.slo_classification == "breached"
            or evidence.deterministic_assessment
        ):
            if assessment not in {
                "alert_supported",
                "evidence_available",
            }:
                raise ValueError(
                    "AI assessment contradicts the available "
                    "deterministic incident evidence."
                )

            return

        if evidence.slo_classification == "insufficient_data":
            if assessment != "insufficient_evidence":
                raise ValueError(
                    "AI assessment contradicts insufficient "
                    "deterministic evidence."
                )

    @staticmethod
    def _validate_provider_evidence(
        payload: dict[str, Any],
        evidence: EvidencePack,
    ) -> None:
        supplied = payload.get("evidence")

        if supplied is None:
            raise ValueError(
                "AI response is missing authoritative evidence."
            )

        if not isinstance(supplied, dict):
            raise ValueError(
                "AI response evidence must be an object."
            )

        expected = evidence.operational_metrics

        if set(supplied) != set(expected):
            raise ValueError(
                "AI response evidence keys do not match "
                "the authoritative evidence."
            )

        for key, expected_value in expected.items():
            actual_value = supplied.get(key)

            if actual_value != expected_value:
                raise ValueError(
                    f"AI modified authoritative evidence: {key}."
                )

    @staticmethod
    def _validate_provider_deployment_correlations(
        payload: dict[str, Any],
        evidence: EvidencePack,
    ) -> None:
        supplied = payload.get(
            "deployment_correlations"
        )

        if supplied is None:
            raise ValueError(
                "AI response is missing deployment correlations."
            )

        if not isinstance(supplied, list):
            raise ValueError(
                "AI deployment_correlations must be a list."
            )

        if supplied != evidence.deployment_correlations:
            raise ValueError(
                "AI modified deterministic deployment correlations."
            )


ai_enrichment_service = AIEnrichmentService()
