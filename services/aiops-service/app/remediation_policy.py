from __future__ import annotations

from .remediation_models import (
    PolicyDecision,
    RemediationAction,
    RemediationPolicyResult,
)


class RemediationPolicy:
    """
    Deterministic policy boundary for AI-assisted remediation.

    AI may recommend an action, but this policy decides whether the
    action is executable.

    Production-changing operations always require explicit human
    approval.

    Unsupported operations are blocked completely.
    """

    BLOCKED_ACTIONS = {
        RemediationAction.RESTART_DEPLOYMENT,
        RemediationAction.SCALE_DEPLOYMENT,
        RemediationAction.ROLLBACK_DEPLOYMENT,
    }

    APPROVAL_REQUIRED_ACTIONS = {
        RemediationAction.RERUN_DEPLOYMENT,
    }

    SAFE_ACTIONS = {
        RemediationAction.ACKNOWLEDGE_INCIDENT,
        RemediationAction.NO_ACTION,
    }

    def evaluate(
        self,
        action: RemediationAction,
        *,
        incident_status: str,
        target_deployment_id: str | None,
    ) -> RemediationPolicyResult:

        if action in self.BLOCKED_ACTIONS:
            return RemediationPolicyResult(
                action=action,
                decision=PolicyDecision.BLOCKED,
                reason=(
                    "Action is not supported by the current "
                    "deployment-service contract. No execution path "
                    "is permitted."
                ),
                requires_human_approval=True,
                executable=False,
            )

        if action == RemediationAction.NO_ACTION:
            return RemediationPolicyResult(
                action=action,
                decision=PolicyDecision.ALLOWED,
                reason="No production change will be performed.",
                requires_human_approval=False,
                executable=True,
            )

        if action == RemediationAction.ACKNOWLEDGE_INCIDENT:
            return RemediationPolicyResult(
                action=action,
                decision=PolicyDecision.ALLOWED,
                reason=(
                    "Acknowledgement changes incident workflow state "
                    "only and does not modify production infrastructure."
                ),
                requires_human_approval=False,
                executable=True,
            )

        if action == RemediationAction.RERUN_DEPLOYMENT:
            if not target_deployment_id:
                return RemediationPolicyResult(
                    action=action,
                    decision=PolicyDecision.BLOCKED,
                    reason=(
                        "A target deployment ID is required for a "
                        "controlled deployment rerun."
                    ),
                    requires_human_approval=True,
                    executable=False,
                )

            return RemediationPolicyResult(
                action=action,
                decision=PolicyDecision.REQUIRES_APPROVAL,
                reason=(
                    "Deployment rerun is supported by the deployment "
                    "service but can change production state. "
                    "Explicit human approval is required."
                ),
                requires_human_approval=True,
                executable=True,
            )

        return RemediationPolicyResult(
            action=action,
            decision=PolicyDecision.BLOCKED,
            reason="Unknown remediation action.",
            requires_human_approval=True,
            executable=False,
        )
