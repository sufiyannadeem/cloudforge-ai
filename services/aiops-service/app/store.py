
from typing import Any

from psycopg.types.json import Jsonb

from .database import get_connection
from .models import (
    AnalysisConfidence,
    Incident,
    IncidentImpact,
    IncidentSeverity,
    IncidentStatus,
)


class IncidentStore:
    def upsert(
        self,
        incident: Incident,
    ) -> Incident:
        with get_connection() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM aiops_incidents
                WHERE fingerprint = %s
                FOR UPDATE
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
                        impact,
                        confidence,
                        analysis_version,
                        priority,
                        summary,
                        probable_cause,
                        root_cause_hints,
                        recommended_actions,
                        labels,
                        annotations,
                        created_at,
                        updated_at,
                        alert_count,
                        raw_alerts
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        incident.id,
                        incident.fingerprint,
                        incident.alert_name,
                        incident.service,
                        incident.severity.value,
                        incident.status.value,
                        incident.impact.value,
                        incident.confidence.value,
                        incident.analysis_version,
                        incident.priority,
                        incident.summary,
                        incident.probable_cause,
                        Jsonb(incident.root_cause_hints),
                        Jsonb(incident.recommended_actions),
                        Jsonb(incident.labels),
                        Jsonb(incident.annotations),
                        incident.created_at,
                        incident.updated_at,
                        incident.alert_count,
                        Jsonb(incident.raw_alerts),
                    ),
                )

                self._insert_event(
                    connection=connection,
                    incident_id=incident.id,
                    event_type="created",
                    message="Incident created from incoming alert.",
                    status=incident.status.value,
                    metadata={
                        "alert_name": incident.alert_name,
                        "service": incident.service,
                        "severity": incident.severity.value,
                        "impact": incident.impact.value,
                        "confidence": incident.confidence.value,
                        "priority": incident.priority,
                        "root_cause_hints": incident.root_cause_hints,
                    },
                    created_at=incident.created_at,
                )

                return incident

            previous_status = existing["status"]
            updated_alert_count = existing["alert_count"] + 1

            existing_raw_alerts = existing["raw_alerts"] or []
            incoming_raw_alerts = incident.raw_alerts or []

            combined_raw_alerts = (
                existing_raw_alerts + incoming_raw_alerts
            )

            updated = connection.execute(
                """
                UPDATE aiops_incidents
                SET severity = %s,
                    status = %s,
                    impact = %s,
                    confidence = %s,
                    analysis_version = %s,
                    priority = %s,
                    summary = %s,
                    probable_cause = %s,
                    root_cause_hints = %s,
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
                    incident.impact.value,
                    incident.confidence.value,
                    incident.analysis_version,
                    incident.priority,
                    incident.summary,
                    incident.probable_cause,
                    Jsonb(incident.root_cause_hints),
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

            if (
                previous_status == IncidentStatus.RESOLVED.value
                and incident.status.value == IncidentStatus.OPEN.value
            ):
                event_type = "reopened"
                message = (
                    "Previously resolved incident reopened "
                    "because a new firing alert was received."
                )
            elif incident.status.value == IncidentStatus.RESOLVED.value:
                event_type = "resolved"
                message = "Incident resolved by incoming alert."
            else:
                event_type = "alert_received"
                message = "Additional alert received for incident."

            self._insert_event(
                connection=connection,
                incident_id=updated["id"],
                event_type=event_type,
                message=message,
                status=incident.status.value,
                metadata={
                    "alert_name": incident.alert_name,
                    "service": incident.service,
                    "severity": incident.severity.value,
                    "impact": incident.impact.value,
                    "confidence": incident.confidence.value,
                    "priority": incident.priority,
                    "root_cause_hints": incident.root_cause_hints,
                    "previous_status": previous_status,
                    "alert_count": updated_alert_count,
                },
                created_at=incident.updated_at,
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

    def get(
        self,
        incident_id: str,
    ) -> Incident | None:
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

    def list_events(
        self,
        incident_id: str,
    ) -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    incident_id,
                    event_type,
                    message,
                    status,
                    metadata,
                    created_at
                FROM aiops_incident_events
                WHERE incident_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (incident_id,),
            ).fetchall()

            return [
                {
                    "id": row["id"],
                    "incident_id": row["incident_id"],
                    "event_type": row["event_type"],
                    "message": row["message"],
                    "status": row["status"],
                    "metadata": row["metadata"] or {},
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def clear(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                TRUNCATE TABLE aiops_incidents
                CASCADE
                """
            )

    @staticmethod
    def _insert_event(
        connection: Any,
        incident_id: str,
        event_type: str,
        message: str,
        status: str,
        metadata: dict[str, Any],
        created_at: Any,
    ) -> None:
        connection.execute(
            """
            INSERT INTO aiops_incident_events (
                incident_id,
                event_type,
                message,
                status,
                metadata,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                incident_id,
                event_type,
                message,
                status,
                Jsonb(metadata),
                created_at,
            ),
        )

    @staticmethod
    def _row_to_incident(
        row: dict[str, Any],
    ) -> Incident:
        return Incident(
            id=row["id"],
            fingerprint=row["fingerprint"],
            alert_name=row["alert_name"],
            service=row["service"],
            severity=IncidentSeverity(
                row["severity"]
            ),
            status=IncidentStatus(
                row["status"]
            ),
            impact=IncidentImpact(
                row.get("impact", "unknown")
            ),
            confidence=AnalysisConfidence(
                row.get("confidence", "low")
            ),
            analysis_version=row.get(
                "analysis_version",
                "1.0",
            ),
            priority=row.get(
                "priority",
                "P4",
            ),
            summary=row["summary"],
            probable_cause=row["probable_cause"],
            root_cause_hints=(
                row.get("root_cause_hints") or []
            ),
            recommended_actions=(
                row["recommended_actions"] or []
            ),
            labels=row["labels"] or {},
            annotations=row["annotations"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            alert_count=row["alert_count"],
            raw_alerts=row["raw_alerts"] or [],
        )


incident_store = IncidentStore()
