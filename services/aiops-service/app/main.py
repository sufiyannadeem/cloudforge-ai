from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .analyzer import analyze_alert
from .database import initialize_database
from .models import (
    AlertmanagerWebhook,
    Incident,
    IncidentListResponse,
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
def list_incidents() -> IncidentListResponse:
    incidents = incident_store.list_all()

    return IncidentListResponse(
        count=len(incidents),
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
