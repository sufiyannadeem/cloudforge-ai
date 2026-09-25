from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .remediation_models import (
    RemediationApprovalRequest,
    RemediationExecutionRequest,
    RemediationPreviewRequest,
    RemediationRejectionRequest,
    RemediationResponse,
)
from .remediation_service import RemediationService


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
            "human_approval_required": False,
            "description": (
                "Acknowledge the incident without modifying "
                "production infrastructure."
            ),
        },
        {
            "action": "no_action",
            "policy": "allowed",
            "human_approval_required": False,
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
):

    try:
        return service.preview(
            incident_id,
            request,
        )
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
):

    proposal = service.remediations.get(proposal_id)

    if proposal is None or proposal.incident_id != incident_id:
        raise HTTPException(
            status_code=404,
            detail="Remediation proposal not found",
        )

    try:
        return service.approve(
            proposal_id,
            request.approved_by.strip(),
        )
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
            request.rejected_by.strip(),
            request.reason.strip(),
        )
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
    "/{incident_id}/remediation/{proposal_id}/execute",
)
def execute_remediation(
    incident_id: str,
    proposal_id: str,
    request: RemediationExecutionRequest,
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
            request.executed_by.strip(),
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

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Remediation execution failed: {exc}",
        ) from exc
