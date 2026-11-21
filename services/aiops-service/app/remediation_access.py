from __future__ import annotations

from fastapi import Depends, HTTPException, Request


def require_remediation_human(request: Request) -> dict[str, str]:
    claims = getattr(request.state, "human_identity", None)
    if not claims:
        raise HTTPException(401, "Verified operator identity required")
    return {"actor": claims["sub"], "role": claims["role"]}


def require_remediation_approver(
    caller: dict[str, str] = Depends(require_remediation_human),
) -> dict[str, str]:
    if caller["role"] not in {"sre", "platform-engineer"}:
        raise HTTPException(403, "SRE or Platform Engineer required.")
    return caller
