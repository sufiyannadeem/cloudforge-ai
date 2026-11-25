from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, Request

from .analysis_service import (
    incident_analysis_service,
)
from .store import incident_store
from .rag import OperationalKnowledgeBase


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incident-intelligence"],
)


@router.post("/{incident_id}/analyze")
def analyze_incident(
    incident_id: str,
    request: Request,
) -> dict:
    """
    Generate incident intelligence for an incident.

    AI is used when an AI provider is configured.
    Otherwise deterministic analysis is persisted.
    """
    import os
    if os.getenv("AI_PROVIDER", "").strip().lower() == "gemini":
        from .isolated_analysis import analyze_project
        analysis = analyze_project(request.state.incident_project)
        incident = incident_store.save_ai_analysis(incident_id, analysis)
        return {"incident": incident, "ai_analysis": analysis}
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


@router.get("/{incident_id}/knowledge")
def incident_knowledge(incident_id: str, response: Response, request: Request) -> dict:
    """Operator-only local references; no provider inference or operational claims."""
    incident = incident_store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    response.headers["Cache-Control"] = "private, no-store"
    from .knowledge_config import knowledge_references
    result = knowledge_references(f"{incident.service} {incident.alert_name}", request.state.incident_project)
    return {"incident_id": incident_id, "authoritative": False, **result}
