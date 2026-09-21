from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Query

from .analyzer import analyze_alert
from .database import initialize_database
from .models import (
    AlertmanagerWebhook,
    Incident,
    IncidentListResponse,
    IncidentStatsResponse,
)
from .store import incident_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="CloudForge AI AIOps Service",
    version="0.2.0",
    description=(
        "Alert ingestion, incident analysis, "
        "and persistent incident storage."
    ),
    lifespan=lifespan,
)

class AcknowledgeIncidentRequest(BaseModel):
    acknowledged_by: str

class AssignIncidentRequest(BaseModel):
    assigned_to: str


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "service": "aiops-service",
        "status": "ok",
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    return {
        "service": "aiops-service",
        "status": "ready",
    }


@app.post("/api/v1/alerts", response_model=list[Incident])
def receive_alerts(
    payload: AlertmanagerWebhook,
) -> list[Incident]:
    incidents: list[Incident] = []

    for alert in payload.alerts:
        incident = analyze_alert(alert)
        stored_incident = incident_store.upsert(incident)
        incidents.append(stored_incident)

    return incidents


@app.get(
    "/api/v1/incidents",
    response_model=IncidentListResponse,
)
def list_incidents(
    status: str | None = Query(
        default=None,
        description="Filter by incident status.",
    ),
    priority: str | None = Query(
        default=None,
        description="Filter by priority: P1, P2, P3, or P4.",
    ),
    impact: str | None = Query(
        default=None,
        description="Filter by impact.",
    ),
    service: str | None = Query(
        default=None,
        description="Filter by service name.",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number.",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of incidents per page.",
    ),
    sort_by: str = Query(
        default="updated_at",
        description=(
            "Sort field: updated_at, created_at, "
            "priority, or alert_count."
        ),
    ),
    sort_order: str = Query(
        default="desc",
        description="Sort direction: asc or desc.",
    ),
) -> IncidentListResponse:
    try:
        incidents, total = incident_store.list_all(
            status=status,
            priority=priority,
            impact=impact,
            service=service,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    total_pages = (
        (total + page_size - 1) // page_size
        if total > 0
        else 0
    )

    return IncidentListResponse(
        count=len(incidents),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        incidents=incidents,
    )


@app.get("/api/v1/incidents/{incident_id}/timeline")
def get_incident_timeline(incident_id: str) -> dict:
    incident = incident_store.get(incident_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    events = incident_store.list_events(incident_id)

    return {
        "incident_id": incident_id,
        "count": len(events),
        "events": events,
    }


@app.get(
    "/api/v1/incidents/stats",
    response_model=IncidentStatsResponse,
)
def get_incident_statistics() -> IncidentStatsResponse:
    statistics = incident_store.get_statistics()

    return IncidentStatsResponse(**statistics)

@app.patch(
    "/api/v1/incidents/{incident_id}/acknowledge",
    response_model=Incident,
)
def acknowledge_incident(
    incident_id: str,
    payload: AcknowledgeIncidentRequest,
) -> Incident:
    acknowledged_by = payload.acknowledged_by.strip()

    if not acknowledged_by:
        raise HTTPException(
            status_code=400,
            detail="acknowledged_by cannot be empty.",
        )

    incident = incident_store.acknowledge(
        incident_id=incident_id,
        acknowledged_by=acknowledged_by,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return incident


@app.get(
    "/api/v1/incidents/{incident_id}",
    response_model=Incident,
)
def get_incident(incident_id: str) -> Incident:
    incident = incident_store.get(incident_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return incident

@app.patch(
    "/api/v1/incidents/{incident_id}/assign",
    response_model=Incident,
)
def assign_incident(
    incident_id: str,
    payload: AssignIncidentRequest,
) -> Incident:
    assigned_to = payload.assigned_to.strip()

    if not assigned_to:
        raise HTTPException(
            status_code=400,
            detail="assigned_to cannot be empty.",
        )

    incident = incident_store.assign(
        incident_id=incident_id,
        assigned_to=assigned_to,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return incident
