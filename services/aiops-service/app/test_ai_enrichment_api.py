from __future__ import annotations

import json
import urllib.error
import urllib.request


BASE_URL = "http://localhost:8090"


def http_get(path: str):
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

        return exc.code, payload


def test_health_endpoint():
    status, payload = http_get("/health")

    assert status == 200
    assert payload["status"] == "ok"


def test_missing_incident_returns_404():
    status, payload = http_get(
        "/api/v1/aiops/incidents/"
        "does-not-exist/enrichment"
    )

    assert status == 404
    assert payload["detail"] == "Incident not found."


def find_existing_incident():
    """
    Retrieve an existing incident from the real
    CloudForge incident API.

    This test does not create or mutate incidents.
    """

    status, payload = http_get(
        "/api/v1/incidents?page=1&page_size=20"
    )

    if status != 200:
        return None

    incidents = payload.get("incidents")

    if not isinstance(incidents, list):
        return None

    if not incidents:
        return None

    return incidents[0]


def test_enrichment_response_contract():
    incident = find_existing_incident()

    if incident is None:
        raise AssertionError(
            "No existing incident was returned by "
            "GET /api/v1/incidents."
        )

    incident_id = incident.get("id")

    assert incident_id

    status, payload = http_get(
        f"/api/v1/aiops/incidents/"
        f"{incident_id}/enrichment"
    )

    assert status == 200

    assert payload["incident_id"] == incident_id

    assert "enrichment" in payload
    assert "evidence" in payload

    enrichment = payload["enrichment"]
    evidence = payload["evidence"]

    assert "status" in enrichment
    assert "provider" in enrichment
    assert "summary" in enrichment
    assert "probable_cause" in enrichment
    assert "confidence" in enrichment

    assert evidence["incident_id"] == incident_id
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

    test_missing_incident_returns_404()
    print("MISSING INCIDENT 404: PASS")

    test_enrichment_response_contract()
    print("ENRICHMENT RESPONSE CONTRACT: PASS")

    print()
    print("ALL AI ENRICHMENT API TESTS PASSED")


if __name__ == "__main__":
    run()
