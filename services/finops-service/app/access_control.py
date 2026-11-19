from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request

from .service_identity import frontend_identity


def require_finops_access(request: Request) -> str:
    role = frontend_identity(request, "finops")["role"]
    configured = os.getenv("FINOPS_ALLOWED_ROLES", "platform-engineer,sre")
    allowed_roles = {value.strip() for value in configured.split(",")} & {"platform-engineer", "sre"}
    if role not in allowed_roles:
        raise HTTPException(403, "FinOps requires a Platform Engineer or SRE")
    return role


def require_pricing_admin(role: str = Depends(require_finops_access)) -> None:
    if role != "platform-engineer":
        raise HTTPException(403, "Pricing changes require a Platform Engineer")
