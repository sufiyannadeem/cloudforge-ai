from __future__ import annotations

from fastapi import APIRouter, HTTPException

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
) -> AIEnrichmentResponse:
    """
    Generate evidence-grounded AI enrichment for an incident.
    """

    result = ai_enrichment_service.enrich(
        incident_id
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found.",
        )

    return result
