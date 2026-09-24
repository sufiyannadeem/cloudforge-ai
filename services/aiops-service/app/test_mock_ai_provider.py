from __future__ import annotations

import json

from app.mock_ai_provider import MockAIProvider


USER_PROMPT = json.dumps(
    {
        "operational_context": {
            "service_up": 1.0,
            "request_rate": 0.1649,
            "error_rate": 0.0,
            "p95_latency_seconds": 0.00475,
            "requests_in_flight": 1.0,
            "deployments_in_progress": 0.0,
            "deployment_failures": None,
            "deployment_total": None,
        },
        "deployment_correlations": [
            {
                "deployment_id": "deployment-1",
                "environment": "development",
                "status": "succeeded",
                "correlation_strength": "high",
                "correlation_type": (
                    "temporal_deployment_correlation"
                ),
            }
        ],
        "deterministic_analysis": {
            "summary": (
                "Evidence-aware deterministic analysis."
            ),
            "probable_cause": (
                "Current operational evidence "
                "is available."
            ),
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
                "request_rate": 0.1649,
                "error_rate": 0.0,
                "p95_latency_seconds": 0.00475,
                "requests_in_flight": 1.0,
                "deployments_in_progress": 0.0,
                "deployment_failures": None,
                "deployment_total": None,
            },
            "evidence_findings": [
                "Service is currently healthy."
            ],
        },
    }
)


def test_valid():
    provider = MockAIProvider(
        mode="valid"
    )

    result = provider.analyze(
        system_prompt="test",
        user_prompt=USER_PROMPT,
    )

    assert result.status == "success"
    assert result.provider == "mock"
    assert result.model == "cloudforge-mock-v1"
    assert result.content

    payload = json.loads(
        result.content
    )

    assert (
        payload["evidence"]["error_rate"]
        == 0.0
    )

    print(
        "MOCK VALID RESPONSE: PASS"
    )


def test_tampered():
    provider = MockAIProvider(
        mode="tampered"
    )

    result = provider.analyze(
        system_prompt="test",
        user_prompt=USER_PROMPT,
    )

    assert result.status == "success"

    payload = json.loads(
        result.content
    )

    assert (
        payload["evidence"]["error_rate"]
        == 99.0
    )

    print(
        "MOCK TAMPERED RESPONSE: PASS"
    )


def test_invalid_json():
    provider = MockAIProvider(
        mode="invalid_json"
    )

    result = provider.analyze(
        system_prompt="test",
        user_prompt=USER_PROMPT,
    )

    assert result.status == "success"
    assert result.content == "{invalid-json"

    print(
        "MOCK INVALID JSON: PASS"
    )


def test_unsupported_assessment():
    provider = MockAIProvider(
        mode="unsupported_assessment"
    )

    result = provider.analyze(
        system_prompt="test",
        user_prompt=USER_PROMPT,
    )

    assert result.status == "success"

    payload = json.loads(
        result.content
    )

    assert (
        payload["assessment"]
        == "root_cause_confirmed"
    )

    print(
        "MOCK UNSUPPORTED ASSESSMENT: PASS"
    )


def test_empty():
    provider = MockAIProvider(
        mode="empty"
    )

    result = provider.analyze(
        system_prompt="test",
        user_prompt=USER_PROMPT,
    )

    assert result.status == "success"
    assert result.content == ""

    print(
        "MOCK EMPTY RESPONSE: PASS"
    )


def main():
    print(
        "========================================"
    )
    print(
        "MOCK AI PROVIDER VALIDATION"
    )
    print(
        "========================================"
    )

    test_valid()
    test_tampered()
    test_invalid_json()
    test_unsupported_assessment()
    test_empty()

    print()
    print(
        "ALL MOCK PROVIDER TESTS PASSED"
    )


if __name__ == "__main__":
    main()
