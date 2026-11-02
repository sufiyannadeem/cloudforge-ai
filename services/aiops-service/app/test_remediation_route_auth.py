from __future__ import annotations

import pytest
from fastapi import HTTPException

from .remediation_access import require_remediation_access


def test_remediation_access_fails_closed_when_token_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFORGE_INTERNAL_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_remediation_access(
            x_cloudforge_internal_token="some-token",
            x_cloudforge_actor="operator",
            x_cloudforge_role="platform-engineer",
        )
    assert exc.value.status_code == 503


def test_remediation_access_rejects_forged_identity_without_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFORGE_INTERNAL_API_TOKEN", "a" * 64)
    with pytest.raises(HTTPException) as exc:
        require_remediation_access(
            x_cloudforge_internal_token="wrong-token",
            x_cloudforge_actor="forged-operator",
            x_cloudforge_role="admin",
        )
    assert exc.value.status_code == 401


def test_remediation_access_returns_trusted_proxy_identity(monkeypatch) -> None:
    token = "test-only-internal-token-32-bytes-minimum"
    monkeypatch.setenv("CLOUDFORGE_INTERNAL_API_TOKEN", token)
    caller = require_remediation_access(
        x_cloudforge_internal_token=token,
        x_cloudforge_actor="operator-1",
        x_cloudforge_role="platform-engineer",
    )
    assert caller == {"actor": "operator-1", "role": "platform-engineer"}


def test_remediation_access_rejects_viewer_role(monkeypatch) -> None:
    token = "test-only-internal-token-32-bytes-minimum"
    monkeypatch.setenv("CLOUDFORGE_INTERNAL_API_TOKEN", token)
    with pytest.raises(HTTPException) as exc:
        require_remediation_access(
            x_cloudforge_internal_token=token,
            x_cloudforge_actor="viewer-1",
            x_cloudforge_role="viewer",
        )
    assert exc.value.status_code == 403
