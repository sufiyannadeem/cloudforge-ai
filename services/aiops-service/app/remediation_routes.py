from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .remediation_models import (
    RemediationApprovalRequest,
    RemediationExecutionRequest,
    RemediationPreviewRequest,
    RemediationRejectionRequest,
    RemediationResponse,
)
from .remediation_service import RemediationService
from .remediation_access import require_remediation_approver, require_remediation_human


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["AI-Ops Remediation"],
)

service = RemediationService()


@router.get(
    "/{incident_id}/remediation",
    response_model=RemediationResponse,
)
def get_remediation(
    incident_id: str,
    caller: dict[str, str] = Depends(require_remediation_human),
) -> RemediationResponse:

    incident = service.incidents.get(incident_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    proposals = service.remediations.list_for_incident(
        incident_id
    )

    available_actions = [
        {
            "action": "acknowledge_incident",
            "policy": "allowed",
            "human_approval_required": True,
            "description": (
                "Acknowledge the incident without modifying "
                "production infrastructure."
            ),
        },
        {
            "action": "no_action",
            "policy": "allowed",
            "human_approval_required": True,
            "description": (
                "Record that no production remediation is required."
            ),
        },
        {
            "action": "rerun_deployment",
            "policy": "requires_approval",
            "human_approval_required": True,
            "description": (
                "Queue an existing pending deployment through "
                "the deployment-service."
            ),
        },
        {
            "action": "restart_deployment",
            "policy": "blocked",
            "human_approval_required": True,
            "description": (
                "Blocked because the current deployment service "
                "does not expose a restart operation."
            ),
        },
        {
            "action": "scale_deployment",
            "policy": "blocked",
            "human_approval_required": True,
            "description": (
                "Blocked because no controlled scaling API exists."
            ),
        },
        {
            "action": "rollback_deployment",
            "policy": "blocked",
            "human_approval_required": True,
            "description": (
                "Blocked because no controlled rollback API exists."
            ),
        },
    ]

    return RemediationResponse(
        incident_id=incident_id,
        available_actions=available_actions,
        proposals=proposals,
    )


@router.post(
    "/{incident_id}/remediation/preview",
)
def preview_remediation(
    incident_id: str,
    request: RemediationPreviewRequest,
    caller: dict[str, str] = Depends(require_remediation_human),
):

    try:
        trusted_request = request.model_copy(update={"requested_by": caller["actor"]})
        return service.preview(incident_id, trusted_request)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from None
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/{incident_id}/remediation/{proposal_id}/approve",
)
def approve_remediation(
    incident_id: str,
    proposal_id: str,
    request: RemediationApprovalRequest,
    caller: dict[str, str] = Depends(require_remediation_approver),
):

    proposal = service.remediations.get(proposal_id)

    if proposal is None or proposal.incident_id != incident_id:
        raise HTTPException(
            status_code=404,
            detail="Remediation proposal not found",
        )

    try:
        return service.approve(proposal_id, caller["actor"], caller["role"], request.expected_version, request.expected_fingerprint)
    except PermissionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/{incident_id}/remediation/{proposal_id}/reject",
)
def reject_remediation(
    incident_id: str,
    proposal_id: str,
    request: RemediationRejectionRequest,
    caller: dict[str, str] = Depends(require_remediation_human),
):

    proposal = service.remediations.get(proposal_id)

    if proposal is None or proposal.incident_id != incident_id:
        raise HTTPException(
            status_code=404,
            detail="Remediation proposal not found",
        )

    try:
        return service.reject(
            proposal_id,
            caller["actor"],
            request.reason.strip() if request.reason else None,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/{incident_id}/remediation/{proposal_id}/execute",
)
def execute_remediation(
    incident_id: str,
    proposal_id: str,
    request: RemediationExecutionRequest,
    caller: dict[str, str] = Depends(require_remediation_approver),
):

    proposal = service.remediations.get(proposal_id)

    if proposal is None or proposal.incident_id != incident_id:
        raise HTTPException(
            status_code=404,
            detail="Remediation proposal not found",
        )

    try:
        return service.execute(
            proposal_id,
            caller["actor"],
            request.idempotency_key.strip(),
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Remediation execution unavailable; review internal audit",
        ) from exc


@router.post(
    "/{incident_id}/remediation/{proposal_id}/verify",
)
def verify_remediation(
    incident_id: str,
    proposal_id: str,
    caller: dict[str, str] = Depends(require_remediation_human),
):

    proposal = service.remediations.get(proposal_id)

    if proposal is None or proposal.incident_id != incident_id:
        raise HTTPException(
            status_code=404,
            detail="Remediation proposal not found",
        )

    try:
        return service.verify(proposal_id)

    except PermissionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Remediation verification failed: {exc}",
        ) from exc


@router.get("/{incident_id}/remediation/history")
def remediation_history(incident_id: str, caller: dict = Depends(require_remediation_human)):
    return {"incident_id": incident_id, "history": service.remediations.history(incident_id)}


@router.post("/{incident_id}/remediation/{proposal_id}/alternative")
def remediation_alternative(incident_id: str, proposal_id: str, caller: dict = Depends(require_remediation_human)):
    proposal=service.remediations.get(proposal_id)
    if proposal is None or proposal.incident_id!=incident_id:
        raise HTTPException(404,"Remediation proposal not found")
    try:
        return service.remediations.alternative(proposal_id,caller['actor'])
    except (ValueError,PermissionError) as exc:
        raise HTTPException(409,str(exc)) from None


@router.get("/{incident_id}/remediation/evidence")
def trusted_remediation_evidence(incident_id: str,caller: dict=Depends(require_remediation_human)):
    try:return service.remediations.evidence_options(incident_id,caller['actor'])
    except (PermissionError,ValueError) as exc:raise HTTPException(409,str(exc)) from None


@router.post("/{incident_id}/remediation/advisories/{effect}/reject")
def reject_local_advisory(incident_id: str,effect: str,request: RemediationRejectionRequest,
                          caller: dict=Depends(require_remediation_human)):
    try:return service.remediations.reject_advisory(incident_id,caller['actor'],effect,request.reason.strip() if request.reason else None)
    except (PermissionError,ValueError) as exc:raise HTTPException(409,str(exc)) from None
