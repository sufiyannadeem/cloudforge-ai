from __future__ import annotations

from .remediation_executor import RemediationExecutor
from .remediation_models import (
    PolicyDecision,
    RemediationAction,
    RemediationPreviewRequest,
    RemediationProposal,
    RemediationStatus,
)
from .remediation_policy import RemediationPolicy
from .remediation_store import RemediationStore
from .store import IncidentStore


class RemediationService:

    def __init__(
        self,
        incident_store: IncidentStore | None = None,
        remediation_store: RemediationStore | None = None,
        policy: RemediationPolicy | None = None,
        executor: RemediationExecutor | None = None,
    ) -> None:
        self.incidents = incident_store or IncidentStore()
        self.remediations = (
            remediation_store or RemediationStore()
        )
        self.policy = policy or RemediationPolicy()
        self.executor = executor or RemediationExecutor()

    def preview(
        self,
        incident_id: str,
        request: RemediationPreviewRequest,
    ) -> RemediationProposal:

        incident = self.incidents.get(incident_id)

        if incident is None:
            raise LookupError("incident not found")

        policy = self.policy.evaluate(
            request.action,
            incident_status=incident.status.value,
            target_deployment_id=request.target_deployment_id,
        )

        if policy.decision == PolicyDecision.BLOCKED:
            status = RemediationStatus.REJECTED
        elif policy.requires_human_approval:
            status = RemediationStatus.PENDING_APPROVAL
        else:
            status = RemediationStatus.APPROVED

        return self.remediations.create(
            incident_id=incident_id,
            action=request.action,
            status=status,
            policy_decision=policy.decision,
            policy_reason=policy.reason,
            reason=request.reason,
            target_deployment_id=request.target_deployment_id,
            proposed_by=request.requested_by,
        )

    def approve(
        self,
        proposal_id: str,
        approved_by: str,
    ) -> RemediationProposal:

        proposal = self.remediations.get(proposal_id)

        if proposal is None:
            raise LookupError("remediation proposal not found")

        if proposal.policy_decision == PolicyDecision.BLOCKED:
            raise PermissionError(
                "blocked remediation proposals cannot be approved"
            )

        result = self.remediations.move_to_approved(
            proposal_id,
            approved_by,
        )

        if result is None:
            raise LookupError("remediation proposal not found")

        return result

    def reject(
        self,
        proposal_id: str,
        rejected_by: str,
        reason: str,
    ) -> RemediationProposal:

        proposal = self.remediations.get(proposal_id)

        if proposal is None:
            raise LookupError("remediation proposal not found")

        result = self.remediations.move_to_rejected(
            proposal_id,
            rejected_by,
            reason,
        )

        if result is None:
            raise LookupError("remediation proposal not found")

        return result

    def execute(
        self,
        proposal_id: str,
        executed_by: str,
    ) -> RemediationProposal:

        proposal = self.remediations.get(proposal_id)

        if proposal is None:
            raise LookupError("remediation proposal not found")

        if proposal.status != RemediationStatus.APPROVED:
            raise PermissionError(
                "only APPROVED remediation proposals can execute"
            )

        if proposal.policy_decision == PolicyDecision.BLOCKED:
            raise PermissionError(
                "blocked remediation proposals cannot execute"
            )

        executing = self.remediations.mark_executing(
            proposal_id,
            executed_by,
        )

        if executing is None:
            raise LookupError("remediation proposal not found")

        try:
            if (
                executing.action
                == RemediationAction.ACKNOWLEDGE_INCIDENT
            ):
                acknowledged = self.incidents.acknowledge(
                    incident_id=executing.incident_id,
                    acknowledged_by=executed_by,
                )

                if acknowledged is None:
                    raise RuntimeError(
                        "incident disappeared during acknowledgement"
                    )

                result = {
                    "action": executing.action.value,
                    "status": "succeeded",
                    "incident_id": executing.incident_id,
                    "acknowledged_by": executed_by,
                }

            else:
                result = self.executor.execute(
                    action=executing.action,
                    incident_id=executing.incident_id,
                    target_deployment_id=(
                        executing.target_deployment_id
                    ),
                    actor=executed_by,
                )

            completed = self.remediations.mark_result(
                proposal_id,
                succeeded=True,
                result=result,
                error=None,
            )

            if completed is None:
                raise RuntimeError(
                    "unable to persist remediation result"
                )

            return completed

        except Exception as exc:
            self.remediations.mark_result(
                proposal_id,
                succeeded=False,
                result={},
                error=str(exc),
            )

            raise
