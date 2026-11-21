from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from .ai_enrichment_models import EnrichmentStatus
from .ai_enrichment_service import AIEnrichmentService
from .ai_provider import AIProviderResult
from .mock_ai_provider import MockAIProvider
from .models import (
    AIAnalysis,
    Incident,
    IncidentSeverity,
    IncidentStatus,
)
from .store import IncidentStore

_TEST_INCIDENT = Incident(
    id="inc-failure-mode-test",
    fingerprint="fp-failure-mode-test",
    alert_name="DeploymentServiceHighLatency",
    service="deployment-service",
    severity=IncidentSeverity.WARNING,
    status=IncidentStatus.OPEN,
    summary="Elevated latency detected on deployment service.",
    probable_cause="Recent deployment rollout.",
    recommended_actions=["Check deployment logs"],
    labels={"service": "deployment-service"},
    annotations={"description": "High latency"},
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
    ai_analysis=AIAnalysis(
        status="deterministic",
        provider="deterministic",
        assessment="evidence_available",
        evidence={},
        evidence_findings=[],
    ),
)


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


@pytest.fixture(autouse=True)
def _mock_incident_store(monkeypatch):
    monkeypatch.setattr(
        IncidentStore,
        "get_by_id",
        lambda self, incident_id: (
            _TEST_INCIDENT if incident_id == _TEST_INCIDENT.id else None
        ),
    )


@pytest.fixture(scope="module")
def incident_id() -> str:
    """
    Pytest fixture backed by an isolated test incident.
    """
    return _TEST_INCIDENT.id


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

    orig_get = IncidentStore.get_by_id
    try:
        IncidentStore.get_by_id = lambda self, incident_id: (
            _TEST_INCIDENT if incident_id == _TEST_INCIDENT.id else None
        )
        incident_id = _TEST_INCIDENT.id

        print(
            f"Using test incident: {incident_id}"
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
    finally:
        IncidentStore.get_by_id = orig_get


if __name__ == "__main__":
    run()
