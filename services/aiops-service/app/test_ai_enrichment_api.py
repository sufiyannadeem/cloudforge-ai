from __future__ import annotations

import asyncio
import base64
import hmac
import json
import os
import time
from datetime import datetime, timezone
import httpx2 as httpx
import pytest

from .main import app
from .models import (
    AIAnalysis,
    Incident,
    IncidentSeverity,
    IncidentStatus,
)
from .store import IncidentStore

def authenticated_get(path):
    key = "aiops-enrichment-test-frontend-key-32-bytes"
    previous = os.environ.get("CLOUDFORGE_FRONTEND_KEY")
    os.environ["CLOUDFORGE_FRONTEND_KEY"] = key
    now = int(time.time())
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss": "frontend", "aud": "aiops", "sub": "operator", "role": "sre",
        "method": "GET", "target": path, "iat": now, "exp": now + 25, "nonce": "01" * 16,
    }).encode()).rstrip(b"=")
    signature = hmac.digest(key.encode(), payload, "sha256").hex()

    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await asyncio.wait_for(client.get(path, headers={"X-CloudForge-Identity": f"{payload.decode()}.{signature}"}), timeout=3)

    try:
        return asyncio.run(send())
    finally:
        if previous is None:
            os.environ.pop("CLOUDFORGE_FRONTEND_KEY", None)
        else:
            os.environ["CLOUDFORGE_FRONTEND_KEY"] = previous


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


@pytest.fixture(autouse=True)
def isolated_evidence(monkeypatch):
    from . import main
    monkeypatch.setattr(main, "claim_telemetry_assertion", lambda *args: True)
    from . import project_evidence
    from .ai_enrichment_service import AIEnrichmentService
    from .ai_enrichment_models import EvidencePack
    from fastapi import HTTPException
    def authorize(incident_id, claims):
        if incident_id != _TEST_INCIDENT.id:
            raise HTTPException(404, "Incident not found.")
        return "00000000-0000-0000-0000-000000000001"
    monkeypatch.setattr(project_evidence, "authorize_incident", authorize)
    monkeypatch.setattr(AIEnrichmentService, "_build_evidence_pack", lambda self, incident: EvidencePack(
        incident_id=incident.id,service=incident.service,alert_name=incident.alert_name,
        incident_summary="Offline fixture", anomaly_classification="normal",slo_classification="insufficient_data"))
    monkeypatch.setattr(AIEnrichmentService, "_build_ai_evidence_package", lambda *args: None)

def test_health_endpoint():
    response = authenticated_get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_missing_incident_returns_404(monkeypatch):
    monkeypatch.setattr(
        IncidentStore,
        "get_by_id",
        lambda self, incident_id: None,
    )

    response = authenticated_get(
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

    response = authenticated_get(
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
