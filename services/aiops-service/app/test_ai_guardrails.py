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


def run():
    validator = AIGuardrailValidator()
    fallback = deterministic_analysis()

    print("========================================")
    print("AI GUARDRAIL VALIDATION")
    print("========================================")

    result = validator.validate(
        valid_payload(fallback),
        fallback,
    )

    assert result.valid
    assert result.analysis is not None

    print("VALID RESPONSE: PASS")

    # ---------------------------------------------------------
    # Evidence tampering
    # ---------------------------------------------------------

    tampered = valid_payload(fallback).replace(
        '"error_rate": 0.0',
        '"error_rate": 99.0',
    )

    result = validator.validate(
        tampered,
        fallback,
    )

    assert not result.valid

    print("EVIDENCE TAMPERING REJECTION: PASS")

    # ---------------------------------------------------------
    # Deployment correlation tampering
    # ---------------------------------------------------------

    tampered = valid_payload(fallback).replace(
        '"correlation_strength": "high"',
        '"correlation_strength": "critical"',
    )

    result = validator.validate(
        tampered,
        fallback,
    )

    assert not result.valid

    print(
        "DEPLOYMENT CORRELATION TAMPERING REJECTION: PASS"
    )

    # ---------------------------------------------------------
    # Unsupported assessment
    # ---------------------------------------------------------

    tampered = valid_payload(fallback).replace(
        '"assessment": "evidence_available"',
        '"assessment": "root_cause_confirmed"',
    )

    result = validator.validate(
        tampered,
        fallback,
    )

    assert not result.valid

    print("UNSUPPORTED ASSESSMENT REJECTION: PASS")

    # ---------------------------------------------------------
    # Invalid JSON
    # ---------------------------------------------------------

    result = validator.validate(
        "not-json",
        fallback,
    )

    assert not result.valid

    print("INVALID JSON REJECTION: PASS")

    # ---------------------------------------------------------
    # Empty response
    # ---------------------------------------------------------

    result = validator.validate(
        "",
        fallback,
    )

    assert not result.valid

    print("EMPTY RESPONSE REJECTION: PASS")

    print()
    print("ALL AI GUARDRAIL TESTS PASSED")


if __name__ == "__main__":
    run()
