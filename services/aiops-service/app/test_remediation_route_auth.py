from __future__ import annotations

import asyncio
import base64
import hmac
import json
import time

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .main import authorize_requests
from .remediation_access import require_remediation_approver, require_remediation_human


@pytest.fixture(autouse=True)
def verified_project_fixture(monkeypatch):
    # This suite checks human/approval identity; ownership/replay deny cases are
    # exercised through actual middleware in test_secure_integration.py.
    from . import main, project_evidence
    monkeypatch.setattr(project_evidence, "authorize_incident", lambda *args: "00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(main, "claim_telemetry_assertion", lambda *args: True)


@pytest.mark.parametrize(
    "case,status",
    [("verified", 200), ("sre", 403), ("developer", 403), ("developer read", 403), ("legacy", 401),
     ("wrong issuer", 401), ("wrong audience", 401), ("wrong action", 401),
     ("expired", 401), ("wrong signature", 401), ("missing key", 503)],
)
def test_remediation_uses_verified_frontend_identity(monkeypatch, case, status):
    key = "test-only-frontend-to-aiops-key-32-bytes"
    if case == "missing key":
        monkeypatch.delenv("CLOUDFORGE_FRONTEND_KEY", raising=False)
    else:
        monkeypatch.setenv("CLOUDFORGE_FRONTEND_KEY", key)
    path = "/api/v1/incidents/incident/remediation/proposal/approve"
    method = "GET" if case == "developer read" else "POST"
    if method == "GET":
        path = "/api/v1/incidents"
    now = int(time.time())
    claims = {
        "iss": "aiops" if case == "wrong issuer" else "frontend",
        "aud": "deployment" if case == "wrong audience" else "aiops",
        "target": path.replace("/approve", "/execute") if case == "wrong action" else path,
        "method": method, "sub": "verified-operator",
        "body": __import__("hashlib").sha256(b"").hexdigest(),
        "role": "developer" if case.startswith("developer") else ("sre" if case == "sre" else "platform-engineer"),
        "iat": now, "exp": now + (-1 if case == "expired" else 25), "nonce": "01" * 16,
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    signature = hmac.digest((key + "wrong" if case == "wrong signature" else key).encode(), payload, "sha256").hex()
    headers = {"X-CloudForge-Actor": "forged", "X-CloudForge-Role": "platform-engineer",
               "X-CloudForge-Internal-Token": key}
    if case != "legacy":
        headers["X-CloudForge-Identity"] = f"{payload.decode()}.{signature}"

    request = Request({
        "type": "http", "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
    })

    request._body = b""

    async def approve(req):
        try:
            actor = require_remediation_approver(require_remediation_human(req))
            return JSONResponse(actor)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    result = asyncio.run(authorize_requests(request, approve))
    assert result.status_code == status
    if status == 200:
        assert json.loads(result.body) == {"actor": "verified-operator", "role": claims["role"]}


def test_alertmanager_credentials_cannot_authorize_human_routes(monkeypatch):
    key = "test-only-alertmanager-identity-32-bytes"
    monkeypatch.setenv("CLOUDFORGE_ALERTMANAGER_KEY", key)
    monkeypatch.setenv("CLOUDFORGE_FRONTEND_KEY", key + "-different")

    async def handle(_):
        return JSONResponse({})

    for path, token, status in [
        ("/api/v1/alerts", key, 200),
        ("/api/v1/alerts", "", 401),
        ("/api/v1/incidents/incident/remediation/proposal/approve", key, 401),
    ]:
        request = Request({
            "type": "http", "method": "POST", "path": path,
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        })
        assert asyncio.run(authorize_requests(request, handle)).status_code == status
