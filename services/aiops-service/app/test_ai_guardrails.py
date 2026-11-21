from __future__ import annotations

from datetime import datetime, timezone

from app.ai_guardrails import (
    AIGuardrailValidator,
)


def deterministic_analysis():
    from app.models import (
        AIAnalysis,
        AnalysisConfidence,
    )

    correlations = [
        {
            "deployment_id": "deployment-1",
            "environment": "development",
            "status": "succeeded",
            "image": "nginx:1.27-alpine",
            "git_commit_sha": "abcdef1234567",
            "namespace": "cloudforge-dev",
            "deployment_created_at": (
                "2026-09-20T18:36:40.037707+00:00"
            ),
            "deployment_updated_at": (
                "2026-09-20T18:37:06.918847+00:00"
            ),
            "incident_time_difference_seconds": 0.0,
            "correlation_type": (
                "temporal_deployment_correlation"
            ),
            "correlation_strength": "high",
            "explanation": (
                "Deployment occurred less than 1 minute "
                "from the incident timestamp. This is a "
                "temporal correlation and does not establish "
                "deployment causation."
            ),
        }
    ]

    return AIAnalysis(
        status="deterministic",
        provider="deterministic",
        model=None,
        summary="Deterministic test analysis.",
        probable_cause=(
            "Current evidence is available."
        ),
        root_cause_hints=[
            "Review deployment timing."
        ],
        recommended_actions=[
            "Inspect service logs."
        ],
        confidence=AnalysisConfidence.MEDIUM,
        assessment="evidence_available",
        evidence={
            "service_up": 1.0,
            "request_rate": 0.1684,
            "error_rate": 0.0,
            "p95_latency_seconds": 0.00475,
            "requests_in_flight": 1.0,
            "deployments_in_progress": 0.0,
            "deployment_failures": None,
            "deployment_total": None,
        },
        evidence_findings=[
            "Service is currently healthy."
        ],
        deployment_correlations=correlations,
        generated_at=datetime.now(
            timezone.utc
        ),
        error=None,
    )


def valid_payload(fallback):
    return """
{
  "model": "test-model",
  "summary": "The service is currently healthy and the incident has supporting operational evidence.",
  "probable_cause": "The available telemetry provides evidence for the incident, but does not establish a confirmed root cause.",
  "root_cause_hints": [
    "Review deployment timing."
  ],
  "recommended_actions": [
    "Inspect service logs."
  ],
  "confidence": "medium",
  "assessment": "evidence_available",
  "evidence": {
    "service_up": 1.0,
    "request_rate": 0.1684,
    "error_rate": 0.0,
    "p95_latency_seconds": 0.00475,
    "requests_in_flight": 1.0,
    "deployments_in_progress": 0.0,
    "deployment_failures": null,
    "deployment_total": null
  },
  "evidence_findings": [
    "Service is currently healthy."
  ],
  "deployment_correlations": [
    {
      "deployment_id": "deployment-1",
      "environment": "development",
      "status": "succeeded",
      "image": "nginx:1.27-alpine",
      "git_commit_sha": "abcdef1234567",
      "namespace": "cloudforge-dev",
      "deployment_created_at": "2026-09-20T18:36:40.037707+00:00",
      "deployment_updated_at": "2026-09-20T18:37:06.918847+00:00",
      "incident_time_difference_seconds": 0.0,
      "correlation_type": "temporal_deployment_correlation",
      "correlation_strength": "high",
      "explanation": "Deployment occurred less than 1 minute from the incident timestamp. This is a temporal correlation and does not establish deployment causation."
    }
  ]
}
"""


def test_valid_response() -> None:
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    result = validator.validate(
        valid_payload(fallback),
        fallback,
        provider="mock",
        model="cloudforge-mock-v1",
    )

    assert result.valid
    assert result.analysis is not None


def test_evidence_tampering_rejected() -> None:
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    tampered = valid_payload(fallback).replace(
        '"error_rate": 0.0',
        '"error_rate": 99.0',
    )

    result = validator.validate(
        tampered,
        fallback,
        provider="mock",
        model="cloudforge-mock-v1",
    )

    assert not result.valid


def test_deployment_correlation_tampering_rejected() -> None:
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    tampered = valid_payload(fallback).replace(
        '"deployment_id": "deployment-1"',
        '"deployment_id": "fake-deployment"',
    )

    result = validator.validate(
        tampered,
        fallback,
        provider="mock",
        model="cloudforge-mock-v1",
    )

    assert not result.valid


def test_unsupported_assessment_rejected() -> None:
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    tampered = valid_payload(fallback).replace(
        '"assessment": "evidence_available"',
        '"assessment": "confirmed_root_cause"',
    )

    result = validator.validate(
        tampered,
        fallback,
        provider="mock",
        model="cloudforge-mock-v1",
    )

    assert not result.valid


def test_invalid_json_rejected() -> None:
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    result = validator.validate(
        "not-json",
        fallback,
        provider="mock",
        model="cloudforge-mock-v1",
    )

    assert not result.valid


def test_empty_response_rejected() -> None:
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    result = validator.validate(
        "",
        fallback,
        provider="mock",
        model="cloudforge-mock-v1",
    )

    assert not result.valid


def test_provider_metadata_is_preserved() -> None:
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    result = validator.validate(
        valid_payload(fallback),
        fallback,
        provider="bedrock",
        model="amazon.nova-lite-v1:0",
    )

    assert result.valid
    assert result.analysis is not None
    assert result.analysis.provider == "bedrock"
    assert result.analysis.model == "amazon.nova-lite-v1:0"


def run() -> None:
    print("========================================")
    print("AI GUARDRAIL VALIDATION")
    print("========================================")

    test_valid_response()
    print("VALID RESPONSE: PASS")

    test_evidence_tampering_rejected()
    print("EVIDENCE TAMPERING REJECTION: PASS")

    test_deployment_correlation_tampering_rejected()
    print("DEPLOYMENT CORRELATION TAMPERING REJECTION: PASS")

    test_unsupported_assessment_rejected()
    print("UNSUPPORTED ASSESSMENT REJECTION: PASS")

    test_invalid_json_rejected()
    print("INVALID JSON REJECTION: PASS")

    test_empty_response_rejected()
    print("EMPTY RESPONSE REJECTION: PASS")

    test_provider_metadata_is_preserved()
    print("PROVIDER METADATA PRESERVATION: PASS")

    print()
    print("ALL AI GUARDRAIL TESTS PASSED")


if __name__ == "__main__":
    run()
