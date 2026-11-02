from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_remediation_access(
    x_cloudforge_internal_token: str | None = Header(
        default=None, alias="X-CloudForge-Internal-Token"
    ),
    x_cloudforge_actor: str | None = Header(
        default=None, alias="X-CloudForge-Actor"
    ),
    x_cloudforge_role: str | None = Header(
        default=None, alias="X-CloudForge-Role"
    ),
) -> dict[str, str]:
    expected = os.getenv("CLOUDFORGE_INTERNAL_API_TOKEN", "")
    if len(expected.encode("utf-8")) < 32 or "replace-with" in expected.lower():
        raise HTTPException(
            status_code=503,
            detail="Remediation authentication is not configured.",
        )

    supplied = (x_cloudforge_internal_token or "").encode("utf-8")
    if not hmac.compare_digest(supplied, expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Service authentication required.")

    actor = (x_cloudforge_actor or "").strip()
    role = (x_cloudforge_role or "").strip().lower()
    if not actor or role not in {"platform-engineer", "devops", "sre", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Authorized operator identity required.",
        )
    return {"actor": actor, "role": role}
