import os
from types import SimpleNamespace

import pytest

from . import finops_anomaly_audit as audit
from .finops_cost_intelligence import CostAnomalyResponse
from .identity_test_helpers import SignedTestClient
from .main import app


PATH = "/api/v1/finops/aws/anomalies/captures"
OPERATOR = {"X-Test-Human-Role": "sre"}


def test_cost_audit_requires_operator_and_configured_database(monkeypatch):
    monkeypatch.setenv("CLOUDFORGE_FRONTEND_KEY", "test-only-frontend-to-finops-key-32-bytes")
    monkeypatch.delenv("FINOPS_AUDIT_DATABASE_URL", raising=False)
    client = SignedTestClient(app)
    assert client.post(PATH).status_code == 401
    assert client.post(PATH, headers={"X-Test-Human-Role": "developer"}).status_code == 403
    assert client.get(PATH, headers=OPERATOR).status_code == 503


def test_cost_audit_persists_server_evidence_and_isolates_accounts(monkeypatch):
    test_dsn = os.getenv("FINOPS_AUDIT_TEST_DATABASE_URL")
    if not test_dsn:
        pytest.skip("isolated PostgreSQL schema not configured")
    monkeypatch.setenv("CLOUDFORGE_FRONTEND_KEY", "test-only-frontend-to-finops-key-32-bytes")
    monkeypatch.setenv("FINOPS_AUDIT_DATABASE_URL", test_dsn)
    account = ["123456789012"]
    estimate = CostAnomalyResponse(
        start_date="2026-01-01", end_date="2026-01-31", threshold=2.5, sample_count=7,
    )
    monkeypatch.setattr(audit, "AWSFinOpsService", lambda: SimpleNamespace(
        client=SimpleNamespace(get_account_id=lambda: account[0]),
        default_cost_intelligence_range=lambda _: ("2026-01-01", "2026-01-31"),
        get_cost_anomalies=lambda **_: estimate,
    ))
    client = SignedTestClient(app)
    result = client.post(PATH, headers=OPERATOR, json={"actor": "forged", "evidence": "made up"})
    assert result.status_code == 201
    saved = result.json()
    assert saved["actor"] == "test-operator" and saved["evidence"]["sample_count"] == 7
    assert client.get(PATH, headers=OPERATOR).json() == [saved]
    account[0] = "987654321098"
    assert client.get(PATH, headers=OPERATOR).json() == []
