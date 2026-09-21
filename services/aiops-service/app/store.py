
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
                SET
                    severity = %s,
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

    def list_all(
        self,
        status: str | None = None,
        priority: str | None = None,
        impact: str | None = None,
        service: str | None = None,
        severity: str | None = None,
        assigned_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[Incident], int]:
        filters: list[str] = []
        parameters: list[Any] = []

        if status is not None:
            filters.append("status = %s")
            parameters.append(status)

        if priority is not None:
            filters.append("priority = %s")
            parameters.append(priority)

        if impact is not None:
            filters.append("impact = %s")
            parameters.append(impact)

        if service is not None:
            filters.append("service = %s")
            parameters.append(service)

        if severity is not None:
            filters.append("severity = %s")
            parameters.append(severity)

        if assigned_to is not None:
            filters.append("assigned_to = %s")
            parameters.append(assigned_to)

        where_clause = ""

        if filters:
            where_clause = "WHERE " + " AND ".join(filters)

        allowed_sort_columns = {
            "updated_at": "updated_at",
            "created_at": "created_at",
            "priority": """
                CASE priority
                    WHEN 'P1' THEN 1
                    WHEN 'P2' THEN 2
                    WHEN 'P3' THEN 3
                    WHEN 'P4' THEN 4
                    ELSE 5
                END
            """,
            "alert_count": "alert_count",
        }

        if sort_by not in allowed_sort_columns:
            raise ValueError("Invalid sort_by value.")

        if sort_order not in {"asc", "desc"}:
            raise ValueError("Invalid sort_order value.")

        sort_expression = allowed_sort_columns[sort_by]
        order_direction = sort_order.upper()

        offset = (page - 1) * page_size

        with get_connection() as connection:
            total_row = connection.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM aiops_incidents
                {where_clause}
                """,
                tuple(parameters),
            ).fetchone()

            total = int(total_row["total"])

            rows = connection.execute(
                f"""
                SELECT *
                FROM aiops_incidents
                {where_clause}
                ORDER BY {sort_expression} {order_direction},
                         updated_at DESC
                LIMIT %s OFFSET %s
                """,
                tuple(parameters + [page_size, offset]),
            ).fetchall()

            incidents = [
                self._row_to_incident(row)
                for row in rows
            ]

            return incidents, total

    def get_statistics(self) -> dict[str, Any]:
        with get_connection() as connection:
            summary = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_incidents,
                    COUNT(*) FILTER (
                        WHERE status = 'open'
                    ) AS open_incidents,
                    COUNT(*) FILTER (
                        WHERE status = 'resolved'
                    ) AS resolved_incidents,
                    COALESCE(SUM(alert_count), 0) AS total_alerts,
                    COALESCE(
                        AVG(alert_count),
                        0
                    ) AS average_alerts_per_incident
                FROM aiops_incidents
                """
            ).fetchone()

            priority_rows = connection.execute(
                """
                SELECT priority, COUNT(*) AS count
                FROM aiops_incidents
                GROUP BY priority
                ORDER BY priority
                """
            ).fetchall()

            impact_rows = connection.execute(
                """
                SELECT impact, COUNT(*) AS count
                FROM aiops_incidents
                GROUP BY impact
                ORDER BY impact
                """
            ).fetchall()

            service_rows = connection.execute(
                """
                SELECT service, COUNT(*) AS count
                FROM aiops_incidents
                GROUP BY service
                ORDER BY count DESC, service
                """
            ).fetchall()

            return {
                "total_incidents": summary["total_incidents"],
                "open_incidents": summary["open_incidents"],
                "resolved_incidents": summary["resolved_incidents"],
                "total_alerts": summary["total_alerts"],
                "average_alerts_per_incident": round(
                    float(summary["average_alerts_per_incident"]),
                    2,
                ),
                "incidents_by_priority": {
                    row["priority"]: row["count"]
                    for row in priority_rows
                },
                "incidents_by_impact": {
                    row["impact"]: row["count"]
                    for row in impact_rows
                },
                "incidents_by_service": {
                    row["service"]: row["count"]
                    for row in service_rows
                },
            }

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

    def acknowledge(
        self,
        incident_id: str,
        acknowledged_by: str,
    ) -> Incident | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE aiops_incidents
                SET
                    acknowledged_at = NOW(),
                    acknowledged_by = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (acknowledged_by, incident_id),
            ).fetchone()

            if row is None:
                return None

            self._insert_event(
                connection=connection,
                incident_id=incident_id,
                event_type="acknowledged",
                message=(
                    f"Incident acknowledged by {acknowledged_by}."
                ),
                status=row["status"],
                metadata={
                    "acknowledged_by": acknowledged_by,
                },
                created_at=row["updated_at"],
            )

            return self._row_to_incident(row)

    def assign(
        self,
        incident_id: str,
        assigned_to: str,
    ) -> Incident | None:
        with get_connection() as connection:
            existing = connection.execute(
                """
                SELECT assigned_to
                FROM aiops_incidents
                WHERE id = %s
                FOR UPDATE
                """,
                (incident_id,),
            ).fetchone()

            if existing is None:
                return None

            previous_assignee = existing["assigned_to"]

            # Prevent duplicate assignment events when the assignee
            # has not changed.
            if previous_assignee == assigned_to:
                row = connection.execute(
                    """
                    SELECT *
                    FROM aiops_incidents
                    WHERE id = %s
                    """,
                    (incident_id,),
                ).fetchone()

                return self._row_to_incident(row)

            row = connection.execute(
                """
                UPDATE aiops_incidents
                SET
                    assigned_to = %s,
                    assigned_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (assigned_to, incident_id),
            ).fetchone()

            if row is None:
                return None

            if previous_assignee:
                message = (
                    f"Incident reassigned from "
                    f"{previous_assignee} to {assigned_to}."
                )
                event_type = "reassigned"
            else:
                message = (
                    f"Incident assigned to {assigned_to}."
                )
                event_type = "assigned"

            self._insert_event(
                connection=connection,
                incident_id=incident_id,
                event_type=event_type,
                message=message,
                status=row["status"],
                metadata={
                    "previous_assignee": previous_assignee,
                    "assigned_to": assigned_to,
                },
                created_at=row["updated_at"],
            )

            return self._row_to_incident(row)

    def unassign(
        self,
        incident_id: str,
    ) -> Incident | None:
        with get_connection() as connection:
            existing = connection.execute(
                """
                SELECT assigned_to
                FROM aiops_incidents
                WHERE id = %s
                FOR UPDATE
                """,
                (incident_id,),
            ).fetchone()

            if existing is None:
                return None

            previous_assignee = existing["assigned_to"]


            if previous_assignee is None:
                row = connection.execute(
                    """
                    SELECT *
                    FROM aiops_incidents
                    WHERE id = %s
                    """,
                    (incident_id,),
                ).fetchone()

                return self._row_to_incident(row)

            row = connection.execute(
                """
                UPDATE aiops_incidents
                SET
                    assigned_to = NULL,
                    assigned_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (incident_id,),
            ).fetchone()

            if row is None:
                return None

            self._insert_event(
                connection=connection,
                incident_id=incident_id,
                event_type="unassigned",
                message=(
                    f"Incident unassigned from "
                    f"{previous_assignee}."
                ),
                status=row["status"],
                metadata={
                    "previous_assignee": previous_assignee,
                },
                created_at=row["updated_at"],
            )

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
            acknowledged_at=row.get("acknowledged_at"),
            acknowledged_by=row.get("acknowledged_by"),
            assigned_to=row.get("assigned_to"),
            assigned_at=row.get("assigned_at"),
            alert_count=row["alert_count"],
            raw_alerts=row["raw_alerts"] or [],
        )


incident_store = IncidentStore()
