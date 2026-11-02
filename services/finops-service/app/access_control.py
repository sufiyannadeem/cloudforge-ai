from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


DEFAULT_ALLOWED_ROLES = {
    "platform-engineer",
    "devops",
    "sre",
    "admin",
}


def _allowed_roles() -> set[str]:
    configured = os.getenv("FINOPS_ALLOWED_ROLES", "")
    if not configured.strip():
        return DEFAULT_ALLOWED_ROLES

    return {
        role.strip().lower()
        for role in configured.split(",")
        if role.strip()
    }


def require_finops_access(
    x_cloudforge_role: str | None = Header(
        default=None,
        alias="X-CloudForge-Role",
    ),
    x_cloudforge_internal_token: str | None = Header(
        default=None,
        alias="X-CloudForge-Internal-Token",
    ),
) -> str:
    expected_token = os.getenv("CLOUDFORGE_INTERNAL_API_TOKEN", "")
    if len(expected_token.encode("utf-8")) < 32 or "replace-with" in expected_token.lower():
        raise HTTPException(
            status_code=503,
            detail="FinOps service authentication is not configured.",
        )

    provided_token = x_cloudforge_internal_token or ""
    if not hmac.compare_digest(
        provided_token.encode("utf-8"), expected_token.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="Service authentication required.",
        )

    role = (x_cloudforge_role or "").strip().lower()
    if not role:
        raise HTTPException(
            status_code=403,
            detail="FinOps access requires an authorized platform role.",
        )

    if role not in _allowed_roles():
        raise HTTPException(
            status_code=403,
            detail="FinOps is restricted to Platform Engineering, DevOps, or SRE roles.",
        )

    return role
