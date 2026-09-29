from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from .ai_enrichment_models import EnrichmentStatus
from .ai_enrichment_service import AIEnrichmentService
from .ai_provider import AIProviderResult
from .mock_ai_provider import MockAIProvider


BASE_URL = "http://localhost:8090"


class FailingAIProvider:
    """
    Test provider that simulates an upstream AI failure.

    It never returns an AI interpretation.
    """

    enabled = True

    def analyze(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        del system_prompt
        del user_prompt

        return AIProviderResult(
            status="error",
            provider="test-provider",
            model="test-model",
            content=None,
            error="Synthetic provider failure.",
        )


class RaisingAIProvider:
    """
    Test provider that simulates an unexpected provider exception.
    """

    enabled = True

    def analyze(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        del system_prompt
        del user_prompt

        raise RuntimeError(
            "Synthetic provider exception."
        )


def http_get(path: str):
    """
    Perform a read-only HTTP GET against the real AIOps service.
    """

    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            body = response.read().decode()

            return (
                response.status,
                json.loads(body),
            )

    except urllib.error.HTTPError as exc:
        body = exc.read().decode()

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {
                "raw": body,
            }

        return (
            exc.code,
            payload,
        )


def find_existing_incident() -> dict[str, Any]:
    """
    Retrieve an existing incident through the real
    CloudForge incident API.

    This test does not create or mutate incidents.
    """

    status, payload = http_get(
        "/api/v1/incidents?page=1&page_size=20"
    )

    if status != 200:
        raise AssertionError(
            "Unable to retrieve incidents from the "
            f"real incident API. HTTP status: {status}"
        )

    incidents = payload.get(
        "incidents"
    )

    if not isinstance(
        incidents,
        list,
    ):
        raise AssertionError(
            "Incident API response does not contain "
            "an 'incidents' list."
        )

    if not incidents:
        raise AssertionError(
            "No existing incident is available for "
            "AI enrichment failure-mode validation."
        )

    incident = incidents[0]

    if not isinstance(
        incident,
        dict,
    ):
        raise AssertionError(
            "Incident API returned an invalid incident object."
        )

    return incident


@pytest.fixture(scope="module")
def incident_id() -> str:
    """
    Pytest fixture backed by an existing incident.

    The fixture is read-only and does not create, update,
    acknowledge, or otherwise mutate incident state.
    """

    incident = find_existing_incident()

    value = incident.get("id")

    if not value:
        raise AssertionError(
            "Existing incident does not contain an ID."
        )

    return str(value)


def run_mode(
    incident_id: str,
    mode: str,
):
    """
    Run the complete AI enrichment service with
    a specific mock-provider failure mode.
    """

    provider = MockAIProvider(
        mode=mode,
    )

    service = AIEnrichmentService(
        provider=provider,
    )

    result = service.enrich(
        incident_id,
    )

    assert result is not None

    return result


def test_valid_response_is_accepted(
    incident_id: str,
) -> None:
    result = run_mode(
        incident_id,
        "valid",
    )

    assert result.enrichment.status == (
        EnrichmentStatus.AI
    )

    assert result.enrichment.provider == "mock"

    assert result.enrichment.model == (
        "cloudforge-mock-v1"
    )

    assert not result.enrichment.guardrail_warnings


def test_tampered_response_falls_back(
    incident_id: str,
) -> None:
    result = run_mode(
        incident_id,
        "tampered",
    )

    assert result.enrichment.status == (
        EnrichmentStatus.FALLBACK
    )

    assert result.enrichment.provider == (
        "deterministic"
    )

    assert result.enrichment.guardrail_warnings

    assert any(
        "rejected" in warning.lower()
        for warning
        in result.enrichment.guardrail_warnings
    )


def test_invalid_json_falls_back(
    incident_id: str,
) -> None:
    result = run_mode(
        incident_id,
        "invalid_json",
    )

    assert result.enrichment.status == (
        EnrichmentStatus.FALLBACK
    )

    assert result.enrichment.provider == (
        "deterministic"
    )

    assert result.enrichment.guardrail_warnings

    assert any(
        "rejected" in warning.lower()
        for warning
        in result.enrichment.guardrail_warnings
    )


def test_unsupported_assessment_falls_back(
    incident_id: str,
) -> None:
    result = run_mode(
        incident_id,
        "unsupported_assessment",
    )

    assert result.enrichment.status == (
        EnrichmentStatus.FALLBACK
    )

    assert result.enrichment.provider == (
        "deterministic"
    )

    assert result.enrichment.guardrail_warnings

    assert any(
        "rejected" in warning.lower()
        for warning
        in result.enrichment.guardrail_warnings
    )


def test_empty_response_falls_back(
    incident_id: str,
) -> None:
    result = run_mode(
        incident_id,
        "empty",
    )

    assert result.enrichment.status == (
        EnrichmentStatus.FALLBACK
    )

    assert result.enrichment.provider == (
        "deterministic"
    )

    assert result.enrichment.guardrail_warnings

    assert any(
        "rejected" in warning.lower()
        for warning
        in result.enrichment.guardrail_warnings
    )


def test_provider_failure_falls_back(
    incident_id: str,
) -> None:
    service = AIEnrichmentService(
        provider=FailingAIProvider(),
    )

    result = service.enrich(
        incident_id,
    )

    assert result is not None

    assert result.enrichment.status == (
        EnrichmentStatus.FALLBACK
    )

    assert result.enrichment.provider == (
        "deterministic"
    )

    assert result.enrichment.error == (
        "Synthetic provider failure."
    )

    assert any(
        "provider failed" in warning.lower()
        for warning
        in result.enrichment.guardrail_warnings
    )


def test_provider_exception_falls_back(
    incident_id: str,
) -> None:
    service = AIEnrichmentService(
        provider=RaisingAIProvider(),
    )

    result = service.enrich(
        incident_id,
    )

    assert result is not None

    assert result.enrichment.status == (
        EnrichmentStatus.FALLBACK
    )

    assert result.enrichment.provider == (
        "deterministic"
    )

    assert result.enrichment.error == (
        "Synthetic provider exception."
    )

    assert any(
        "unexpected exception" in warning.lower()
        for warning
        in result.enrichment.guardrail_warnings
    )


def test_fallback_preserves_deterministic_evidence(
    incident_id: str,
) -> None:
    result = run_mode(
        incident_id,
        "tampered",
    )

    assert result.enrichment.status == (
        EnrichmentStatus.FALLBACK
    )

    assert result.enrichment.provider == (
        "deterministic"
    )

    assert result.evidence.incident_id == (
        incident_id
    )

    assert result.evidence.service

    assert result.evidence.alert_name

    assert isinstance(
        result.evidence.operational_metrics,
        dict,
    )

    assert isinstance(
        result.evidence.evidence_findings,
        list,
    )


def run() -> None:
    print("========================================")
    print(
        "AI ENRICHMENT FAILURE-MODE E2E VALIDATION"
    )
    print("========================================")

    incident = find_existing_incident()

    incident_id = incident.get("id")

    if not incident_id:
        raise AssertionError(
            "Existing incident does not contain an ID."
        )

    print(
        f"Using existing incident: {incident_id}"
    )

    test_valid_response_is_accepted(
        incident_id
    )
    print("VALID AI RESPONSE: PASS")

    test_tampered_response_falls_back(
        incident_id
    )
    print("TAMPERED AI RESPONSE → FALLBACK: PASS")

    test_invalid_json_falls_back(
        incident_id
    )
    print("INVALID JSON → FALLBACK: PASS")

    test_unsupported_assessment_falls_back(
        incident_id
    )
    print(
        "UNSUPPORTED ASSESSMENT → FALLBACK: PASS"
    )

    test_empty_response_falls_back(
        incident_id
    )
    print("EMPTY RESPONSE → FALLBACK: PASS")

    test_provider_failure_falls_back(
        incident_id
    )
    print("PROVIDER FAILURE → FALLBACK: PASS")

    test_provider_exception_falls_back(
        incident_id
    )
    print(
        "PROVIDER EXCEPTION → FALLBACK: PASS"
    )

    test_fallback_preserves_deterministic_evidence(
        incident_id
    )
    print(
        "DETERMINISTIC EVIDENCE PRESERVED: PASS"
    )

    print("========================================")
    print("ALL FAILURE-MODE CHECKS PASSED")
    print("========================================")


if __name__ == "__main__":
    run()
