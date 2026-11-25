"""Authorization precedes collection; ownership is never taken from alert labels."""
import math
import time
from uuid import UUID
from fastapi import HTTPException
from .database import get_connection
from .prometheus_client import PrometheusClient


def authorize_incident(incident_id: str, claims: dict) -> str:
    if claims.get('role') not in {'sre','platform-engineer'}:
        raise HTTPException(403,'Operator permission required')
    try:
        with get_connection(connect_timeout=2) as db:
            db.execute("SET LOCAL statement_timeout='2s'")
            row=db.execute('''
                SELECT b.project_id FROM aiops_incident_projects b
                JOIN projects p ON p.id=b.project_id
                JOIN auth_users u ON u.username=%s AND u.active AND u.role=%s
                WHERE b.incident_id=%s AND p.created_by IS NOT NULL
                  AND (p.created_by=u.username OR EXISTS(
                    SELECT 1 FROM project_members m WHERE m.project_id=p.id AND m.username=u.username
                    AND m.level IN ('viewer','maintainer')))
            ''',(claims['sub'],claims['role'],incident_id)).fetchone()
        if not row:
            raise HTTPException(404,'Incident project access denied or ownership unknown')
        return str(UUID(str(row['project_id'])))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503,'Incident ownership authorization unavailable') from None


def aggregate_evidence(project_id: str, client=None) -> list[dict]:
    from .trusted_telemetry import project_signals
    return [{"signal":item["signal"],"state":item["state"]}
            for item in project_signals(project_id,client,internal=False)]


def membership_filter(claims: dict) -> tuple[str, tuple]:
    """Correlated filter reused by list/stat APIs so persisted AI cannot leak via listings."""
    if claims.get('role') not in {'sre','platform-engineer'}:
        return 'FALSE', ()
    return '''EXISTS (
        SELECT 1 FROM aiops_incident_projects b
        JOIN projects p ON p.id=b.project_id
        JOIN auth_users u ON u.username=%s AND u.active AND u.role=%s
        WHERE b.incident_id=aiops_incidents.id AND p.created_by IS NOT NULL
          AND (p.created_by=u.username OR EXISTS (
            SELECT 1 FROM project_members m WHERE m.project_id=p.id AND m.username=u.username
            AND m.level IN ('viewer','maintainer')))
    )''', (claims['sub'],claims['role'])
