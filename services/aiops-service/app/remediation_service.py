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
from .remediation_verifier import (
    DeploymentVerificationClient,
    RemediationVerificationError,
)
from .store import IncidentStore


class RemediationService:
    def __init__(
        self,
        incident_store: IncidentStore | None = None,
        remediation_store: RemediationStore | None = None,
        executor: RemediationExecutor | None = None,
        policy: RemediationPolicy | None = None,
        verifier: DeploymentVerificationClient | None = None,
        *,
        store: RemediationStore | None = None,
    ) -> None:
        self.incidents = (
            incident_store
            if incident_store is not None
            else IncidentStore()
        )

        self.remediations = (
            remediation_store
            if remediation_store is not None
            else (
                store
                if store is not None
                else RemediationStore()
            )
        )

        self.store = self.remediations

        self.executor = (
            executor
            if executor is not None
            else RemediationExecutor()
        )

        self.policy = (
            policy
            if policy is not None
            else RemediationPolicy()
        )

        self.verifier = (
            verifier
            if verifier is not None
            else DeploymentVerificationClient()
        )

    def get(
        self,
        proposal_id: str,
    ) -> RemediationProposal | None:
        return self.remediations.get(proposal_id)

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
            raise LookupError(
                "remediation proposal not found"
            )

        if proposal.policy_decision == PolicyDecision.BLOCKED:
            raise PermissionError(
                "blocked remediation proposals cannot be approved"
            )

        result = self.remediations.move_to_approved(
            proposal_id,
            approved_by,
        )

        if result is None:
            raise LookupError(
                "remediation proposal not found"
            )

        if result.status == RemediationStatus.EXPIRED:
            raise PermissionError(
                "remediation proposal has expired"
            )

        return result

    def reject(
        self,
        proposal_id: str,
        rejected_by: str,
        reason: str,
    ) -> RemediationProposal:
        proposal = self.remediations.get(proposal_id)

        if proposal is None:
            raise LookupError(
                "remediation proposal not found"
            )

        result = self.remediations.move_to_rejected(
            proposal_id,
            rejected_by,
            reason,
        )

        if result is None:
            raise LookupError(
                "remediation proposal not found"
            )

        if result.status == RemediationStatus.EXPIRED:
            raise PermissionError(
                "remediation proposal has expired"
            )

        return result

    def execute(
        self,
        proposal_id: str,
        executed_by: str,
        idempotency_key: str,
    ) -> RemediationProposal:
        """
        Execute an approved remediation.

        Asynchronous deployment reruns:

            APPROVED
                ↓
            EXECUTING
                ↓
            VERIFYING

        Verification is performed separately so the API request does
        not block while deployment-service executes the deployment.
        """

        idempotency_key = idempotency_key.strip()

        if len(idempotency_key) < 8:
            raise ValueError(
                "idempotency_key must contain at least 8 characters"
            )

        proposal = self.remediations.get(proposal_id)

        if proposal is None:
            raise LookupError(
                "remediation proposal not found"
            )

        if proposal.execution_idempotency_key:
            if (
                proposal.execution_idempotency_key
                != idempotency_key
            ):
                raise PermissionError(
                    "remediation proposal has already "
                    "been executed with a different "
                    "idempotency key"
                )

            return proposal

        if proposal.status in {
            RemediationStatus.SUCCEEDED,
            RemediationStatus.FAILED,
            RemediationStatus.VERIFYING,
            RemediationStatus.EXPIRED,
        }:
            raise PermissionError(
                "remediation proposal has already "
                "completed or is currently being verified"
            )

        if proposal.status != RemediationStatus.APPROVED:
            raise PermissionError(
                "only APPROVED remediation proposals "
                "can execute"
            )

        if proposal.policy_decision == PolicyDecision.BLOCKED:
            raise PermissionError(
                "blocked remediation proposals cannot execute"
            )

        executing = self.remediations.claim_execution(
            proposal_id,
            executed_by,
            idempotency_key,
        )

        if executing is None:
            raise LookupError(
                "remediation proposal not found"
            )

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

            if (
                executing.action
                == RemediationAction.RERUN_DEPLOYMENT
            ):
                if not executing.target_deployment_id:
                    raise ValueError(
                        "target_deployment_id is required"
                    )

                baseline = self.verifier.snapshot(
                    executing.target_deployment_id
                )

                result = self.executor.execute(
                    action=executing.action,
                    incident_id=executing.incident_id,
                    target_deployment_id=(
                        executing.target_deployment_id
                    ),
                    actor=executed_by,
                )

                verifying = self.remediations.mark_verifying(
                    proposal_id,
                    result={
                        "execution": result,
                        "baseline": baseline,
                    },
                )

                if verifying is None:
                    raise RuntimeError(
                        "unable to transition remediation "
                        "to VERIFYING"
                    )

                return verifying

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

    def verify(
        self,
        proposal_id: str,
    ) -> RemediationProposal:
        proposal = self.remediations.get(proposal_id)

        if proposal is None:
            raise LookupError(
                "remediation proposal not found"
            )

        if proposal.status in {
            RemediationStatus.SUCCEEDED,
            RemediationStatus.FAILED,
        }:
            return proposal

        if proposal.status != RemediationStatus.VERIFYING:
            raise PermissionError(
                "only VERIFYING remediation proposals "
                "can be verified"
            )

        if (
            proposal.action
            != RemediationAction.RERUN_DEPLOYMENT
        ):
            raise PermissionError(
                "only deployment reruns require "
                "post-action verification"
            )

        if not proposal.target_deployment_id:
            raise ValueError(
                "target_deployment_id is required for verification"
            )

        verification_context = (
            proposal.verification_result or {}
        )

        baseline = verification_context.get(
            "baseline",
            {},
        )

        baseline_attempt = baseline.get(
            "baseline_attempt_number"
        )

        if baseline_attempt is None:
            baseline_attempt = baseline.get(
                "attempt_number"
            )

        if baseline_attempt is None:
            raise ValueError(
                "verification baseline attempt number is missing"
            )

        try:
            verification = self.verifier.verify_rerun(
                proposal.target_deployment_id,
                int(baseline_attempt),
            )

            verified = bool(
                verification.get(
                    "verified",
                    False,
                )
            )

            error = None

            if not verified:
                error = verification.get(
                    "error_message"
                )

                if not error:
                    error = verification.get(
                        "error"
                    )

            result = self.remediations.mark_verified(
                proposal_id,
                succeeded=verified,
                verification_result={
                    "execution": verification_context.get(
                        "execution",
                        {},
                    ),
                    "baseline": baseline,
                    "verification": verification,
                },
                error=error,
            )

            if result is None:
                raise RuntimeError(
                    "unable to persist remediation "
                    "verification result"
                )

            return result

        except RemediationVerificationError as exc:
            # The deployment outcome is UNKNOWN.
            #
            # A verification outage, timeout, malformed response,
            # or unavailable deployment-service must NOT be treated
            # as evidence that the remediation itself failed.
            retryable_result = {
                "execution": verification_context.get(
                    "execution",
                    {},
                ),
                "baseline": baseline,
                "verification": {
                    "verified": False,
                    "status": "verification_unavailable",
                    "retryable": True,
                    "error": str(exc),
                },
            }

            result = self.remediations.record_verification_attempt(
                proposal_id,
                retryable_result,
            )

            if result is None:
                raise RuntimeError(
                    "unable to persist retryable "
                    "verification state"
                ) from exc

            return result
