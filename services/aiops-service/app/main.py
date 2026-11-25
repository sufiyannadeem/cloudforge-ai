import hmac

import psycopg
from starlette.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .service_identity import frontend_identity, production_database
from .analysis_routes import router as incident_intelligence_router
from .remediation_routes import router as remediation_router
from .anomaly_routes import router as anomaly_router
from .ai_enrichment_routes import router as ai_enrichment_router
from .slo_routes import router as slo_router


from .analyzer import analyze_alert
from .database import claim_telemetry_assertion, initialize_database
from .models import (
    AlertmanagerWebhook,
    Incident,
    IncidentListResponse,
    IncidentStatsResponse,
)
from .store import incident_store


import logging
import os
from .aws_secrets_loader import populate_env_from_secrets_manager

logger = logging.getLogger("cloudforge.aiops")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Attempt Secrets Manager retrieval at startup if configured
    try:
        populate_env_from_secrets_manager(service_name="aiops-service")
    except Exception as exc:
        logger.error("Failed to load secrets during startup: %s", exc)
        if os.getenv("APP_ENV") == "production":
            raise

    # 2. In production, ensure required secrets and configuration are present and valid
    if os.getenv("APP_ENV") == "production":
        token = os.getenv("CLOUDFORGE_FRONTEND_KEY", "")
        if len(token) < 32 or "replace-with" in token.lower():
            raise RuntimeError(
                "CLOUDFORGE_FRONTEND_KEY must be configured with at least 32 characters in production"
            )
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url or "localhost" in db_url or "replace-with" in db_url:
            raise RuntimeError(
                "DATABASE_URL must be configured with valid production credentials in production"
            )

        # Mock AI provider is strictly for tests and local development; never allowed in production
        ai_provider_mode = os.getenv("AI_PROVIDER", "").strip().lower()
        if ai_provider_mode == "mock":
            raise RuntimeError(
                "AI_PROVIDER 'mock' is not permitted in production. "
                "Production must use an explicit, approved provider (e.g. 'bedrock') or 'disabled'."
            )


    production_database(os.getenv("DATABASE_URL", ""), "cf_aiops")
    if os.getenv("APP_ENV") != "production":
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

@app.middleware("http")
async def authorize_requests(request: Request, call_next):
    path = request.url.path
    if request.method == "GET" and path in {"/health", "/ready"}:
        return await call_next(request)
    if request.method == "POST" and path == "/api/v1/alerts":
        key = os.getenv("CLOUDFORGE_ALERTMANAGER_KEY", "")
        supplied = request.headers.get("Authorization", "")
        if (
            len(key.encode()) < 32 or "replace-with" in key.lower()
            or key in {os.getenv("CLOUDFORGE_FRONTEND_KEY"), os.getenv("CLOUDFORGE_AIOPS_DEPLOYMENT_KEY")}
            or not hmac.compare_digest(supplied.encode(), f"Bearer {key}".encode())
        ):
            return JSONResponse({"detail": "Alertmanager identity required"}, status_code=401)
        return await call_next(request)

    try:
        claims = frontend_identity(request, "aiops")
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    if claims["role"] == "developer":
        return JSONResponse({"detail": "Operator permission required"}, status_code=403)
    if request.method == "GET" and path in {
        "/api/v1/slo/summary", "/api/v1/slo/definitions", "/api/v1/anomalies/summary",
    }:
        try:
            claimed = await run_in_threadpool(claim_telemetry_assertion, claims["nonce"], claims["exp"])
        except (psycopg.Error, RuntimeError):
            return JSONResponse({"detail": "Telemetry authorization unavailable"}, status_code=503)
        if not claimed:
            return JSONResponse({"detail": "Invalid or replayed service identity"}, status_code=401)
    if request.method == "POST" and "/remediation" in path:
        import hashlib
        expected_body = claims.get("body")
        if not isinstance(expected_body, str) or len(expected_body) != 64:
            return JSONResponse({"detail": "Body-bound review identity required"}, status_code=401)
        import asyncio
        payload = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    payload.extend(chunk)
                    if len(payload) > 16384:
                        return JSONResponse({"detail": "Review request too large"}, status_code=413)
        except TimeoutError:
            return JSONResponse({"detail": "Review request timed out"}, status_code=408)
        request._body = bytes(payload)
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_body):
            return JSONResponse({"detail": "Review request body mismatch"}, status_code=401)
    # Gate every incident intelligence read/analysis before loading evidence.
    import re
    match = re.fullmatch(r"/api/v1/(?:aiops/)?incidents/([^/]+)/(enrichment|knowledge|ai-analysis|analyze(?:/deterministic)?)", path)
    detail = re.fullmatch(r"/api/v1/incidents/([^/]+)(?:/.*)?", path)
    if detail and detail[1] == "stats":
        detail = None
    if match or detail:
        from .project_evidence import authorize_incident
        try:
            request.state.incident_project = await run_in_threadpool(authorize_incident, (match or detail)[1], claims)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        if request.method == "POST" or (match and match[2] == "enrichment"):
            try:
                if not await run_in_threadpool(claim_telemetry_assertion, claims["nonce"], claims["exp"]):
                    return JSONResponse({"detail": "Replayed service identity"}, status_code=401)
            except Exception:
                return JSONResponse({"detail": "Replay authorization unavailable"}, status_code=503)
    request.state.human_identity = claims
    response = await call_next(request)
    if "/incidents" in path:
        response.headers["Cache-Control"] = "private, no-store"
    return response


app.include_router(
    incident_intelligence_router
)

app.include_router(
    remediation_router
)
app.include_router(
    slo_router
)
app.include_router(
    anomaly_router
)
app.include_router(
    ai_enrichment_router
)

class AcknowledgeIncidentRequest(BaseModel):
    acknowledged_by: str

class AssignIncidentRequest(BaseModel):
    assigned_to: str

class ResolveIncidentRequest(BaseModel):
    resolved_by: str
    resolution_notes: str


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "service": "aiops-service",
        "status": "ok",
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    # Connectivity is bounded and failure details never leave the health endpoint.
    for name in ['DATABASE_URL']:
        dsn = os.getenv(name)
        if not dsn:
            if os.getenv("APP_ENV") == "production":
                raise HTTPException(status_code=503, detail="Database readiness unavailable")
            continue
        try:
            production_database(dsn, "cf_aiops")
            with psycopg.connect(dsn, connect_timeout=2, autocommit=True,
                                 options="-c statement_timeout=1000") as db:
                db.execute("SELECT 1")
        except (psycopg.Error, RuntimeError):
            raise HTTPException(status_code=503, detail="Database readiness unavailable") from None
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
    request: Request,
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
    severity: str | None = Query(
        default=None,
        description="Filter by severity: info, warning, or critical.",
    ),
    assigned_to: str | None = Query(
        default=None,
        description="Filter by assigned engineer.",
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
            claims=request.state.human_identity,
            status=status,
            priority=priority,
            impact=impact,
            service=service,
            severity=severity,
            assigned_to=assigned_to,
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
def get_incident_statistics(request: Request) -> IncidentStatsResponse:
    statistics = incident_store.get_statistics(claims=request.state.human_identity)

    return IncidentStatsResponse(**statistics)

@app.patch(
    "/api/v1/incidents/{incident_id}/acknowledge",
    response_model=Incident,
)
def acknowledge_incident(
    incident_id: str,
    payload: AcknowledgeIncidentRequest,
    http_request: Request,
) -> Incident:
    acknowledged_by = http_request.state.human_identity["sub"]

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

@app.patch(
    "/api/v1/incidents/{incident_id}/resolve",
    response_model=Incident,
)
def resolve_incident(
    incident_id: str,
    request: ResolveIncidentRequest,
    http_request: Request,
) -> Incident:
    resolved_by = http_request.state.human_identity["sub"]
    resolution_notes = request.resolution_notes.strip()

    if not resolved_by:
        raise HTTPException(
            status_code=422,
            detail="resolved_by cannot be empty.",
        )

    if not resolution_notes:
        raise HTTPException(
            status_code=422,
            detail="resolution_notes cannot be empty.",
        )

    incident = incident_store.resolve(
        incident_id=incident_id,
        resolved_by=resolved_by,
        resolution_notes=resolution_notes,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found.",
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

@app.delete(
    "/api/v1/incidents/{incident_id}/assign",
    response_model=Incident,
)
def unassign_incident(
    incident_id: str,
) -> Incident:
    incident = incident_store.unassign(
        incident_id=incident_id,
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return incident
