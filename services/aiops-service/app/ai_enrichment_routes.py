from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .ai_enrichment_models import AIEnrichmentResponse
from .ai_enrichment_service import ai_enrichment_service


router = APIRouter(
    prefix="/api/v1/aiops",
    tags=["AIOps AI Enrichment"],
)


@router.get(
    "/incidents/{incident_id}/enrichment",
    response_model=AIEnrichmentResponse,
)
def get_incident_enrichment(
    incident_id: str,
    request: Request,
) -> AIEnrichmentResponse:
    """
    Generate evidence-grounded AI enrichment for an incident.
    """

    import os
    if os.getenv("AI_PROVIDER", "").strip().lower() == "gemini":
        from .isolated_analysis import analyze_project
        from .ai_enrichment_models import AIEnrichment, EvidencePack
        analysis = analyze_project(request.state.incident_project)
        return AIEnrichmentResponse(incident_id=incident_id,
            enrichment=AIEnrichment(status="ai" if analysis.status == "success" else "fallback",
                provider=analysis.provider, model=analysis.model, summary=analysis.summary or "Unavailable",
                probable_cause=analysis.probable_cause or "Causality is not established.",
                confidence=analysis.confidence.value, evidence_used=analysis.evidence_findings,
                error=analysis.error, citations=analysis.citations,
                retrieval_status=analysis.retrieval_status, knowledge_references=analysis.knowledge_references),
            evidence=EvidencePack(incident_id=incident_id,service="project",alert_name="project_signals",
                                  incident_summary="Project-scoped aggregate evidence"))
    result = ai_enrichment_service.enrich(
        incident_id
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found.",
        )

    return result
