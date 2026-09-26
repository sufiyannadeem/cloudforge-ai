from __future__ import annotations

import json

from app.ai_enrichment_guardrails import (
    AIEnrichmentGuardrailError,
    AIEnrichmentGuardrails,
)
from app.ai_enrichment_models import (
    AIEnrichment,
    EnrichmentConfidence,
    EnrichmentStatus,
    EvidencePack,
)


def evidence_pack() -> EvidencePack:
    return EvidencePack(
        incident_id="inc-123",
        service="deployment-service",
        alert_name="HighLatency",
        incident_summary="Deployment service latency increased.",
        deterministic_assessment=(
            "Prometheus reports elevated latency."
        ),
        evidence_findings=[
            "P95 latency is elevated.",
            "A deployment occurred near the incident.",
        ],
        operational_metrics={
            "p95_latency_seconds": 1.82,
            "request_rate": 0.42,
        },
        anomaly_classification="critical",
        anomaly_metrics=[
            {
                "name": "p95_latency",
                "current_value": 1.82,
                "baseline_value": 0.42,
            }
        ],
        slo_classification="breached",
        slo_results=[
            {
                "name": "P95 Latency",
                "status": "breached",
            }
        ],
        deployment_correlations=[
            {
                "deployment_id": "dep-123",
                "correlation_type": "temporal",
                "incident_time_difference_seconds": 120.0,
            }
        ],
    )


def valid_enrichment() -> AIEnrichment:
    return AIEnrichment(
        status=EnrichmentStatus.AI,
        provider="mock",
        model="mock-model",
        summary=(
            "The incident is associated with elevated latency "
            "and a critical anomaly signal."
        ),
        probable_cause=(
            "The available evidence is consistent with a "
            "recent service change contributing to latency."
        ),
        contributing_signals=[
            "P95 latency anomaly.",
            "SLO latency breach.",
        ],
        investigation_steps=[
            "Review the correlated deployment.",
            "Compare latency before and after the deployment.",
        ],
        confidence=EnrichmentConfidence.MEDIUM,
        evidence_used=[
            "P95 latency is elevated.",
            "A deployment occurred near the incident.",
        ],
    )


def test_valid_enrichment_passes() -> None:
    validator = AIEnrichmentGuardrails()

    result = validator.validate(
        valid_enrichment(),
        evidence_pack(),
    )

    assert result.status == EnrichmentStatus.AI


def test_causal_claim_is_rejected() -> None:
    validator = AIEnrichmentGuardrails()

    enrichment = valid_enrichment()
    enrichment.probable_cause = (
        "The deployment caused the latency incident."
    )

    try:
        validator.validate(
            enrichment,
            evidence_pack(),
        )
    except AIEnrichmentGuardrailError as exc:
        assert "causal" in str(exc).lower()
    else:
        raise AssertionError(
            "Unsupported causal claim was accepted."
        )


def test_high_confidence_without_evidence_is_rejected() -> None:
    validator = AIEnrichmentGuardrails()

    enrichment = valid_enrichment()
    enrichment.confidence = EnrichmentConfidence.HIGH

    evidence = EvidencePack(
        incident_id="inc-123",
        service="deployment-service",
        alert_name="Unknown",
        incident_summary="No evidence.",
    )

    try:
        validator.validate(
            enrichment,
            evidence,
        )
    except AIEnrichmentGuardrailError as exc:
        assert "evidence" in str(exc).lower()
    else:
        raise AssertionError(
            "High-confidence response without evidence was accepted."
        )


def test_unsupported_evidence_reference_is_rejected() -> None:
    validator = AIEnrichmentGuardrails()

    enrichment = valid_enrichment()
    enrichment.evidence_used = [
        "Database CPU is 99 percent."
    ]

    try:
        validator.validate(
            enrichment,
            evidence_pack(),
        )
    except AIEnrichmentGuardrailError as exc:
        assert "evidence" in str(exc).lower()
    else:
        raise AssertionError(
            "Unsupported evidence reference was accepted."
        )


def test_json_payload_shape_is_serializable() -> None:
    enrichment = valid_enrichment()

    encoded = json.dumps(
        enrichment.model_dump(mode="json")
    )

    assert "summary" in encoded
    assert "probable_cause" in encoded


def test_provider_tampered_evidence_is_rejected() -> None:
    from app.ai_enrichment_service import AIEnrichmentService

    evidence = evidence_pack()

    payload = {
        "assessment": "evidence_available",
        "confidence": "medium",
        "summary": "Valid summary.",
        "probable_cause": (
            "The evidence does not establish a confirmed root cause."
        ),
        "evidence": dict(evidence.operational_metrics),
        "deployment_correlations": (
            evidence.deployment_correlations
        ),
    }

    payload["evidence"]["p95_latency_seconds"] = 99.0

    try:
        AIEnrichmentService._validate_provider_evidence(
            payload,
            evidence,
        )
    except ValueError as exc:
        assert "authoritative evidence" in str(exc)
    else:
        raise AssertionError(
            "Tampered provider evidence was accepted."
        )


def test_provider_unsupported_assessment_is_rejected() -> None:
    from app.ai_enrichment_service import AIEnrichmentService

    evidence = evidence_pack()

    payload = {
        "assessment": "root_cause_confirmed",
    }

    try:
        AIEnrichmentService._validate_provider_assessment(
            payload,
            evidence,
        )
    except ValueError as exc:
        assert "unsupported assessment" in str(exc)
    else:
        raise AssertionError(
            "Unsupported assessment was accepted."
        )


def test_provider_assessment_mismatch_is_rejected() -> None:
    from app.ai_enrichment_service import AIEnrichmentService

    evidence = evidence_pack()

    payload = {
        "assessment": "alert_not_currently_observed",
    }

    try:
        AIEnrichmentService._validate_provider_assessment(
            payload,
            evidence,
        )
    except ValueError as exc:
        assert "contradicts" in str(exc).lower()
    else:
        raise AssertionError(
            "Assessment mismatch was accepted."
        )


def test_provider_deployment_correlations_are_authoritative() -> None:
    from app.ai_enrichment_service import AIEnrichmentService

    evidence = evidence_pack()

    payload = {
        "deployment_correlations": [],
    }

    try:
        AIEnrichmentService._validate_provider_deployment_correlations(
            payload,
            evidence,
        )
    except ValueError as exc:
        assert "deployment correlations" in str(exc)
    else:
        raise AssertionError(
            "Modified deployment correlations were accepted."
        )


def test_empty_provider_response_is_rejected() -> None:
    from app.ai_enrichment_service import AIEnrichmentService

    try:
        AIEnrichmentService._parse_provider_response(
            "",
            provider="mock",
            model="cloudforge-mock-v1",
            evidence=evidence_pack(),
        )
    except ValueError as exc:
        assert "empty response" in str(exc)
    else:
        raise AssertionError(
            "Empty provider response was accepted."
        )


def test_invalid_json_provider_response_is_rejected() -> None:
    from app.ai_enrichment_service import AIEnrichmentService

    try:
        AIEnrichmentService._parse_provider_response(
            "{invalid-json",
            provider="mock",
            model="cloudforge-mock-v1",
            evidence=evidence_pack(),
        )
    except Exception as exc:
        assert isinstance(exc, Exception)
    else:
        raise AssertionError(
            "Invalid JSON provider response was accepted."
        )


def test_valid_provider_payload_is_accepted() -> None:
    from app.ai_enrichment_service import AIEnrichmentService

    evidence = evidence_pack()

    payload = {
        "assessment": "evidence_available",
        "confidence": "medium",
        "summary": (
            "The evidence supports the observed incident "
            "condition."
        ),
        "probable_cause": (
            "The available evidence is consistent with "
            "a recent service change contributing to latency."
        ),
        "contributing_signals": [
            "P95 latency anomaly.",
            "SLO latency breach.",
        ],
        "investigation_steps": [
            "Review the correlated deployment.",
        ],
        "causality": (
            "Temporal or contextual correlation only; "
            "causality is not established."
        ),
        "evidence_used": [
            "P95 latency is elevated.",
        ],
        "evidence": dict(evidence.operational_metrics),
        "deployment_correlations": (
            evidence.deployment_correlations
        ),
    }

    enrichment = AIEnrichmentService._parse_provider_response(
        json.dumps(payload),
        provider="mock",
        model="cloudforge-mock-v1",
        evidence=evidence,
    )

    assert enrichment.status == EnrichmentStatus.AI
    assert enrichment.confidence == EnrichmentConfidence.MEDIUM


def test_cautious_root_cause_statement_is_allowed() -> None:
    validator = AIEnrichmentGuardrails()

    enrichment = valid_enrichment()
    enrichment.probable_cause = (
        "The evidence does not establish a confirmed root cause."
    )

    result = validator.validate(
        enrichment,
        evidence_pack(),
    )

    assert result.status == EnrichmentStatus.AI


def test_cautious_causality_statement_is_allowed() -> None:
    validator = AIEnrichmentGuardrails()

    enrichment = valid_enrichment()
    enrichment.causality = (
        "Temporal correlation does not establish causality."
    )

    result = validator.validate(
        enrichment,
        evidence_pack(),
    )

    assert result.status == EnrichmentStatus.AI


def test_root_cause_assertion_is_rejected() -> None:
    validator = AIEnrichmentGuardrails()

    enrichment = valid_enrichment()
    enrichment.probable_cause = (
        "The deployment was the root cause of the incident."
    )

    try:
        validator.validate(
            enrichment,
            evidence_pack(),
        )
    except AIEnrichmentGuardrailError as exc:
        assert "causal" in str(exc).lower()
    else:
        raise AssertionError(
            "Root-cause assertion was accepted."
        )


def test_confirmed_root_cause_assertion_is_rejected() -> None:
    validator = AIEnrichmentGuardrails()

    enrichment = valid_enrichment()
    enrichment.probable_cause = (
        "The deployment has been confirmed as the root cause."
    )

    try:
        validator.validate(
            enrichment,
            evidence_pack(),
        )
    except AIEnrichmentGuardrailError as exc:
        assert "causal" in str(exc).lower()
    else:
        raise AssertionError(
            "Confirmed root-cause assertion was accepted."
        )
