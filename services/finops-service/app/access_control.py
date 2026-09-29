from __future__ import annotations

import os

from fastapi import Header, HTTPException


DEFAULT_ALLOWED_ROLES = {
    "platform-engineer",
    "devops",
    "sre",
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
) -> str:
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
