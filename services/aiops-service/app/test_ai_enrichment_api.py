from __future__ import annotations

from datetime import datetime, timezone
from fastapi.testclient import TestClient

from .main import app
from .models import (
    AIAnalysis,
    Incident,
    IncidentSeverity,
    IncidentStatus,
)
from .store import IncidentStore

client = TestClient(app)

_TEST_INCIDENT = Incident(
    id="inc-enrichment-test",
    fingerprint="fp-enrichment-test",
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


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_missing_incident_returns_404(monkeypatch):
    monkeypatch.setattr(
        IncidentStore,
        "get_by_id",
        lambda self, incident_id: None,
    )

    response = client.get(
        "/api/v1/aiops/incidents/does-not-exist/enrichment"
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"] == "Incident not found."


def test_enrichment_response_contract(monkeypatch):
    monkeypatch.setattr(
        IncidentStore,
        "get_by_id",
        lambda self, incident_id: (
            _TEST_INCIDENT if incident_id == _TEST_INCIDENT.id else None
        ),
    )

    response = client.get(
        f"/api/v1/aiops/incidents/{_TEST_INCIDENT.id}/enrichment"
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["incident_id"] == _TEST_INCIDENT.id
    assert "enrichment" in payload
    assert "evidence" in payload

    enrichment = payload["enrichment"]
    evidence = payload["evidence"]

    assert "status" in enrichment
    assert "provider" in enrichment
    assert "summary" in enrichment
    assert "probable_cause" in enrichment
    assert "confidence" in enrichment

    assert evidence["incident_id"] == _TEST_INCIDENT.id
    assert "service" in evidence
    assert "alert_name" in evidence
    assert "operational_metrics" in evidence
    assert "anomaly_classification" in evidence
    assert "slo_classification" in evidence
    assert "deployment_correlations" in evidence


def run():
    print("========================================")
    print("AI ENRICHMENT API VALIDATION")
    print("========================================")

    test_health_endpoint()
    print("HEALTH ENDPOINT: PASS")

    orig_get = IncidentStore.get_by_id
    try:
        IncidentStore.get_by_id = lambda self, incident_id: None
        test_missing_incident_returns_404(
            type("MonkeyPatch", (), {"setattr": staticmethod(lambda obj, name, val: setattr(obj, name, val))})()
        )
        print("MISSING INCIDENT 404: PASS")

        IncidentStore.get_by_id = lambda self, incident_id: (
            _TEST_INCIDENT if incident_id == _TEST_INCIDENT.id else None
        )
        test_enrichment_response_contract(
            type("MonkeyPatch", (), {"setattr": staticmethod(lambda obj, name, val: setattr(obj, name, val))})()
        )
        print("ENRICHMENT RESPONSE CONTRACT: PASS")
    finally:
        IncidentStore.get_by_id = orig_get

    print()
    print("ALL AI ENRICHMENT API TESTS PASSED")


if __name__ == "__main__":
    run()
