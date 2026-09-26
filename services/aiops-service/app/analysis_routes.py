from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .analysis_service import (
    incident_analysis_service,
)
from .store import incident_store


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-intelligence"],
)


@router.post("/{incident_id}/analyze")
def analyze_incident(
    incident_id: str,
) -> dict:
    """
    Generate incident intelligence for an incident.

    AI is used when an AI provider is configured.
    Otherwise deterministic analysis is persisted.
    """
    incident = incident_analysis_service.analyze_incident(
        incident_id=incident_id,
        incident_store=incident_store,
        use_ai=True,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found.",
        )

    return {
        "incident": incident,
        "ai_analysis": incident.ai_analysis,
    }


@router.post("/{incident_id}/analyze/deterministic")
def analyze_incident_deterministic(
    incident_id: str,
) -> dict:
    """
    Run deterministic incident analysis without
    calling an external AI provider.
    """
    incident = incident_analysis_service.analyze_incident(
        incident_id=incident_id,
        incident_store=incident_store,
        use_ai=False,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found.",
        )

    return {
        "incident": incident,
        "ai_analysis": incident.ai_analysis,
    }


@router.get("/{incident_id}/ai-analysis")
def get_ai_analysis(
    incident_id: str,
) -> dict:
    """
    Return the persisted AI analysis.
    """
    incident = incident_store.get(
        incident_id
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found.",
        )

    return {
        "incident_id": incident_id,
        "ai_analysis": incident.ai_analysis,
    }
