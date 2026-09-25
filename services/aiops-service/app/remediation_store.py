from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from .database import get_connection
from .remediation_models import (
    PolicyDecision,
    RemediationAction,
    RemediationProposal,
    RemediationStatus,
)


class RemediationStore:

    def create(
        self,
        *,
        incident_id: str,
        action: RemediationAction,
        status: RemediationStatus,
        policy_decision: PolicyDecision,
        policy_reason: str,
        reason: str | None,
        target_deployment_id: str | None,
        proposed_by: str,
    ) -> RemediationProposal:

        now = datetime.now(timezone.utc)
        proposal_id = (
            f"rem-{now.strftime('%Y%m%d%H%M%S%f')}"
        )

        with get_connection() as connection:
            row = connection.execute(
                """
                INSERT INTO aiops_remediation_proposals (
                    id,
                    incident_id,
                    action,
                    status,
                    policy_decision,
                    policy_reason,
                    reason,
                    target_deployment_id,
                    proposed_by,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    proposal_id,
                    incident_id,
                    action.value,
                    status.value,
                    policy_decision.value,
                    policy_reason,
                    reason,
                    target_deployment_id,
                    proposed_by,
                    now,
                    now,
                ),
            ).fetchone()

            self._event(
                connection,
                incident_id,
                "remediation_proposed",
                (
                    f"Remediation proposal {proposal_id} created "
                    f"for action {action.value}."
                ),
                status.value,
                {
                    "proposal_id": proposal_id,
                    "action": action.value,
                    "policy_decision": policy_decision.value,
                    "target_deployment_id": target_deployment_id,
                    "proposed_by": proposed_by,
                },
                now,
            )

            return self._row_to_model(row)

    def get(
        self,
        proposal_id: str,
    ) -> RemediationProposal | None:

        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM aiops_remediation_proposals
                WHERE id = %s
                """,
                (proposal_id,),
            ).fetchone()

            if row is None:
                return None

            return self._row_to_model(row)

    def list_for_incident(
        self,
        incident_id: str,
    ) -> list[RemediationProposal]:

        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM aiops_remediation_proposals
                WHERE incident_id = %s
                ORDER BY created_at DESC
                """,
                (incident_id,),
            ).fetchall()

            return [
                self._row_to_model(row)
                for row in rows
            ]

    def move_to_approved(
        self,
        proposal_id: str,
        approved_by: str,
    ) -> RemediationProposal | None:

        now = datetime.now(timezone.utc)

        with get_connection() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM aiops_remediation_proposals
                WHERE id = %s
                FOR UPDATE
                """,
                (proposal_id,),
            ).fetchone()

            if existing is None:
                return None

            if existing["status"] != RemediationStatus.PENDING_APPROVAL.value:
                raise ValueError(
                    "only PENDING_APPROVAL proposals can be approved"
                )

            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    status = %s,
                    approved_by = %s,
                    approved_at = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    RemediationStatus.APPROVED.value,
                    approved_by,
                    now,
                    now,
                    proposal_id,
                ),
            ).fetchone()

            self._event(
                connection,
                row["incident_id"],
                "remediation_approved",
                (
                    f"Remediation proposal {proposal_id} "
                    f"approved by {approved_by}."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "approved_by": approved_by,
                    "action": row["action"],
                },
                now,
            )

            return self._row_to_model(row)

    def move_to_rejected(
        self,
        proposal_id: str,
        rejected_by: str,
        reason: str,
    ) -> RemediationProposal | None:

        now = datetime.now(timezone.utc)

        with get_connection() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM aiops_remediation_proposals
                WHERE id = %s
                FOR UPDATE
                """,
                (proposal_id,),
            ).fetchone()

            if existing is None:
                return None

            if existing["status"] != RemediationStatus.PENDING_APPROVAL.value:
                raise ValueError(
                    "only PENDING_APPROVAL proposals can be rejected"
                )

            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    status = %s,
                    rejected_by = %s,
                    rejection_reason = %s,
                    rejected_at = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    RemediationStatus.REJECTED.value,
                    rejected_by,
                    reason,
                    now,
                    now,
                    proposal_id,
                ),
            ).fetchone()

            self._event(
                connection,
                row["incident_id"],
                "remediation_rejected",
                (
                    f"Remediation proposal {proposal_id} "
                    f"rejected by {rejected_by}."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "rejected_by": rejected_by,
                    "reason": reason,
                    "action": row["action"],
                },
                now,
            )

            return self._row_to_model(row)

    def mark_executing(
        self,
        proposal_id: str,
        requested_by: str,
    ) -> RemediationProposal | None:

        now = datetime.now(timezone.utc)

        with get_connection() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM aiops_remediation_proposals
                WHERE id = %s
                FOR UPDATE
                """,
                (proposal_id,),
            ).fetchone()

            if existing is None:
                return None

            if existing["status"] != RemediationStatus.APPROVED.value:
                raise ValueError(
                    "only APPROVED proposals can be executed"
                )

            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    status = %s,
                    execution_requested_by = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    RemediationStatus.EXECUTING.value,
                    requested_by,
                    now,
                    proposal_id,
                ),
            ).fetchone()

            self._event(
                connection,
                row["incident_id"],
                "remediation_executing",
                (
                    f"Remediation proposal {proposal_id} "
                    f"entered execution."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "requested_by": requested_by,
                    "action": row["action"],
                },
                now,
            )

            return self._row_to_model(row)

    def mark_result(
        self,
        proposal_id: str,
        *,
        succeeded: bool,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> RemediationProposal | None:

        now = datetime.now(timezone.utc)
        status = (
            RemediationStatus.SUCCEEDED
            if succeeded
            else RemediationStatus.FAILED
        )

        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    status = %s,
                    result = %s,
                    error = %s,
                    executed_at = %s,
                    updated_at = %s
                WHERE id = %s
                  AND status = %s
                RETURNING *
                """,
                (
                    status.value,
                    Jsonb(result or {}),
                    error,
                    now,
                    now,
                    proposal_id,
                    RemediationStatus.EXECUTING.value,
                ),
            ).fetchone()

            if row is None:
                return None

            self._event(
                connection,
                row["incident_id"],
                (
                    "remediation_succeeded"
                    if succeeded
                    else "remediation_failed"
                ),
                (
                    f"Remediation proposal {proposal_id} "
                    f"{status.value.lower()}."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "action": row["action"],
                    "error": error,
                    "result": result or {},
                },
                now,
            )

            return self._row_to_model(row)

    @staticmethod
    def _event(
        connection: Any,
        incident_id: str,
        event_type: str,
        message: str,
        status: str,
        metadata: dict[str, Any],
        created_at: datetime,
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
    def _row_to_model(
        row: dict[str, Any],
    ) -> RemediationProposal:

        return RemediationProposal(
            id=row["id"],
            incident_id=row["incident_id"],
            action=RemediationAction(row["action"]),
            status=RemediationStatus(row["status"]),
            policy_decision=PolicyDecision(
                row["policy_decision"]
            ),
            policy_reason=row["policy_reason"],
            reason=row["reason"],
            target_deployment_id=row[
                "target_deployment_id"
            ],
            proposed_by=row["proposed_by"],
            approved_by=row["approved_by"],
            rejected_by=row["rejected_by"],
            rejection_reason=row["rejection_reason"],
            execution_requested_by=row[
                "execution_requested_by"
            ],
            result=row["result"] or {},
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            rejected_at=row["rejected_at"],
            executed_at=row["executed_at"],
        )


remediation_store = RemediationStore()
