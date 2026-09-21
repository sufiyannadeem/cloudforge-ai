from typing import Any

from psycopg.types.json import Jsonb

from .database import get_connection
from .models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
)


class IncidentStore:
    def upsert(self, incident: Incident) -> Incident:
        with get_connection() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM aiops_incidents
                WHERE fingerprint = %s
                """,
                (incident.fingerprint,),
            ).fetchone()

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO aiops_incidents (
                        id,
                        fingerprint,
                        alert_name,
                        service,
                        severity,
                        status,
                        summary,
                        probable_cause,
                        recommended_actions,
                        labels,
                        annotations,
                        created_at,
                        updated_at,
                        alert_count,
                        raw_alerts
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        incident.id,
                        incident.fingerprint,
                        incident.alert_name,
                        incident.service,
                        incident.severity.value,
                        incident.status.value,
                        incident.summary,
                        incident.probable_cause,
                        Jsonb(incident.recommended_actions),
                        Jsonb(incident.labels),
                        Jsonb(incident.annotations),
                        incident.created_at,
                        incident.updated_at,
                        incident.alert_count,
                        Jsonb(incident.raw_alerts),
                    ),
                )

                return incident

            updated_alert_count = existing["alert_count"] + 1
            existing_raw_alerts = existing["raw_alerts"] or []
            incoming_raw_alerts = incident.raw_alerts or []

            combined_raw_alerts = (
                existing_raw_alerts + incoming_raw_alerts
            )

            updated = connection.execute(
                """
                UPDATE aiops_incidents
                SET
                    severity = %s,
                    status = %s,
                    summary = %s,
                    probable_cause = %s,
                    recommended_actions = %s,
                    labels = %s,
                    annotations = %s,
                    updated_at = %s,
                    alert_count = %s,
                    raw_alerts = %s
                WHERE fingerprint = %s
                RETURNING *
                """,
                (
                    incident.severity.value,
                    incident.status.value,
                    incident.summary,
                    incident.probable_cause,
                    Jsonb(incident.recommended_actions),
                    Jsonb(incident.labels),
                    Jsonb(incident.annotations),
                    incident.updated_at,
                    updated_alert_count,
                    Jsonb(combined_raw_alerts),
                    incident.fingerprint,
                ),
            ).fetchone()

            if updated is None:
                raise RuntimeError(
                    "Incident update failed unexpectedly."
                )

            return self._row_to_incident(updated)

    def list_all(self) -> list[Incident]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM aiops_incidents
                ORDER BY updated_at DESC
                """
            ).fetchall()

            return [
                self._row_to_incident(row)
                for row in rows
            ]

    def get(self, incident_id: str) -> Incident | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM aiops_incidents
                WHERE id = %s
                """,
                (incident_id,),
            ).fetchone()

            if row is None:
                return None

            return self._row_to_incident(row)

    def clear(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                TRUNCATE TABLE aiops_incidents
                """
            )

    @staticmethod
    def _row_to_incident(row: dict[str, Any]) -> Incident:
        return Incident(
            id=row["id"],
            fingerprint=row["fingerprint"],
            alert_name=row["alert_name"],
            service=row["service"],
            severity=IncidentSeverity(row["severity"]),
            status=IncidentStatus(row["status"]),
            summary=row["summary"],
            probable_cause=row["probable_cause"],
            recommended_actions=row["recommended_actions"] or [],
            labels=row["labels"] or {},
            annotations=row["annotations"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            alert_count=row["alert_count"],
            raw_alerts=row["raw_alerts"] or [],
        )


incident_store = IncidentStore()
