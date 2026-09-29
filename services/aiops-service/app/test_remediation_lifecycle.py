
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from .remediation_models import (
    PolicyDecision,
    RemediationAction,
    RemediationProposal,
    RemediationStatus,
)
from .remediation_service import RemediationService
from .remediation_verifier import RemediationVerificationError


class FakeIncidentStore:

    def __init__(self) -> None:
        self.acknowledged = []

    def get(self, incident_id: str):
        return type(
            "Incident",
            (),
            {
                "id": incident_id,
                "status": type(
                    "Status",
                    (),
                    {
                        "value": "open",
                    },
                )(),
            },
        )()

    def acknowledge(
        self,
        incident_id: str,
        acknowledged_by: str,
    ):
        self.acknowledged.append(
            {
                "incident_id": incident_id,
                "acknowledged_by": acknowledged_by,
            }
        )

        return {
            "incident_id": incident_id,
            "acknowledged_by": acknowledged_by,
        }


class FakeRemediationStore:

    def __init__(
        self,
        proposal: RemediationProposal,
    ) -> None:
        self.proposal = proposal
        self.claim_calls = 0
        self.mark_result_calls = 0
        self.mark_verifying_calls = 0
        self.mark_verified_calls = 0
        self.record_verification_attempt_calls = 0

    def get(
        self,
        proposal_id: str,
    ) -> RemediationProposal | None:

        if self.proposal.id != proposal_id:
            return None

        return self.proposal

    def claim_execution(
        self,
        proposal_id: str,
        executed_by: str,
        idempotency_key: str,
    ) -> RemediationProposal | None:

        if self.proposal.id != proposal_id:
            return None

        self.claim_calls += 1

        if self.proposal.execution_idempotency_key:

            if (
                self.proposal.execution_idempotency_key
                != idempotency_key
            ):
                raise PermissionError(
                    "proposal has already been executed "
                    "with a different idempotency key"
                )

            return self.proposal

        self.proposal = self.proposal.model_copy(
            update={
                "status": RemediationStatus.EXECUTING,
                "execution_requested_by": executed_by,
                "execution_idempotency_key": idempotency_key,
            }
        )

        return self.proposal

    def mark_result(
        self,
        proposal_id: str,
        *,
        succeeded: bool,
        result: dict,
        error: str | None,
    ) -> RemediationProposal | None:

        if self.proposal.id != proposal_id:
            return None

        self.mark_result_calls += 1

        self.proposal = self.proposal.model_copy(
            update={
                "status": (
                    RemediationStatus.SUCCEEDED
                    if succeeded
                    else RemediationStatus.FAILED
                ),
                "result": result,
                "error": error,
            }
        )

        return self.proposal

    def mark_verifying(
        self,
        proposal_id: str,
        *,
        result: dict,
    ) -> RemediationProposal | None:

        if self.proposal.id != proposal_id:
            return None

        self.mark_verifying_calls += 1

        now = datetime.now(timezone.utc)

        self.proposal = self.proposal.model_copy(
            update={
                "status": RemediationStatus.VERIFYING,
                "verification_started_at": now,
                "verification_result": result,
            }
        )

        return self.proposal

    def record_verification_attempt(
        self,
        proposal_id: str,
        result: dict,
    ) -> RemediationProposal | None:

        if self.proposal.id != proposal_id:
            return None

        self.record_verification_attempt_calls += 1

        existing_result = (
            self.proposal.verification_result
            if isinstance(
                self.proposal.verification_result,
                dict,
            )
            else {}
        )

        self.proposal = self.proposal.model_copy(
            update={
                "status": RemediationStatus.VERIFYING,
                "verification_result": {
                    **existing_result,
                    "last_verification": result,
                },
                "error": (
                    result.get("verification", {}).get("error")
                    if isinstance(
                        result.get("verification"),
                        dict,
                    )
                    else None
                ),
            }
        )

        return self.proposal

    def mark_verified(
        self,
        proposal_id: str,
        *,
        succeeded: bool,
        verification_result: dict,
        error: str | None,
    ) -> RemediationProposal | None:

        if self.proposal.id != proposal_id:
            return None

        self.mark_verified_calls += 1

        now = datetime.now(timezone.utc)

        self.proposal = self.proposal.model_copy(
            update={
                "status": (
                    RemediationStatus.SUCCEEDED
                    if succeeded
                    else RemediationStatus.FAILED
                ),
                "verified_at": now,
                "verification_result": verification_result,
                "error": error,
            }
        )

        return self.proposal


class FakeExecutor:

    def __init__(
        self,
        result: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or {
            "action": "no_action",
            "status": "succeeded",
        }
        self.error = error
        self.calls = 0

    def execute(
        self,
        *,
        action,
        incident_id: str,
        target_deployment_id: str | None,
        actor: str,
    ):

        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.result


class FakeVerifier:

    def __init__(
        self,
        baseline: dict | None = None,
        verification: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        self.baseline = baseline or {
            "baseline_attempt_number": 0,
            "baseline_attempt_id": None,
        }

        self.verification = verification or {
            "verified": True,
            "status": "succeeded",
            "attempt_number": (
                self.baseline.get(
                    "baseline_attempt_number",
                    0,
                )
                + 1
            ),
        }

        self.error = error
        self.snapshot_calls = 0
        self.verify_calls = 0

    def snapshot(
        self,
        deployment_id: str,
    ) -> dict:

        self.snapshot_calls += 1

        if self.error is not None:
            raise self.error

        return self.baseline

    def verify_rerun(
        self,
        deployment_id: str,
        baseline_attempt_number: int,
    ) -> dict:

        self.verify_calls += 1

        if self.error is not None:
            raise self.error

        return self.verification


def make_proposal(
    *,
    action: RemediationAction = RemediationAction.NO_ACTION,
    status: RemediationStatus = RemediationStatus.APPROVED,
    policy_decision: PolicyDecision = PolicyDecision.ALLOWED,
    target_deployment_id: str | None = None,
    idempotency_key: str | None = None,
) -> RemediationProposal:

    now = datetime.now(timezone.utc)

    return RemediationProposal(
        id="rem-1",
        incident_id="incident-1",
        action=action,
        status=status,
        policy_decision=policy_decision,
        policy_reason="test policy",
        reason="test remediation",
        target_deployment_id=target_deployment_id
        if target_deployment_id is not None
        else (
            "deployment-1"
            if action == RemediationAction.RERUN_DEPLOYMENT
            else None
        ),
        proposed_by="test-user",
        approved_by=(
            "test-approver"
            if status
            in {
                RemediationStatus.APPROVED,
                RemediationStatus.EXECUTING,
                RemediationStatus.VERIFYING,
                RemediationStatus.SUCCEEDED,
                RemediationStatus.FAILED,
            }
            else None
        ),
        rejected_by=None,
        rejection_reason=None,
        execution_requested_by=(
            "operator"
            if status
            in {
                RemediationStatus.EXECUTING,
                RemediationStatus.VERIFYING,
                RemediationStatus.SUCCEEDED,
                RemediationStatus.FAILED,
            }
            else None
        ),
        result={},
        error=None,
        created_at=now,
        updated_at=now,
        approved_at=(
            now
            if status
            in {
                RemediationStatus.APPROVED,
                RemediationStatus.EXECUTING,
                RemediationStatus.VERIFYING,
                RemediationStatus.SUCCEEDED,
                RemediationStatus.FAILED,
            }
            else None
        ),
        rejected_at=None,
        executed_at=(
            now
            if status
            in {
                RemediationStatus.SUCCEEDED,
                RemediationStatus.FAILED,
            }
            else None
        ),
        expires_at=None,
        verification_started_at=(
            now
            if status == RemediationStatus.VERIFYING
            else None
        ),
        verified_at=(
            now
            if status
            in {
                RemediationStatus.SUCCEEDED,
                RemediationStatus.FAILED,
            }
            else None
        ),
        verification_result={},
        execution_idempotency_key=idempotency_key,
    )


def make_service(
    proposal: RemediationProposal,
    *,
    executor: FakeExecutor | None = None,
    verifier: FakeVerifier | None = None,
):
    store = FakeRemediationStore(proposal)

    service = RemediationService(
        incident_store=FakeIncidentStore(),
        remediation_store=store,
        executor=executor or FakeExecutor(),
        verifier=verifier or FakeVerifier(),
    )

    return service, store


def test_same_idempotency_key_does_not_execute_twice():

    proposal = make_proposal()

    executor = FakeExecutor()

    service, store = make_service(
        proposal,
        executor=executor,
    )

    first = service.execute(
        "rem-1",
        "operator",
        "idempotency-key-123",
    )

    second = service.execute(
        "rem-1",
        "operator",
        "idempotency-key-123",
    )

    assert first.id == "rem-1"
    assert second.id == "rem-1"

    assert executor.calls == 1
    assert store.claim_calls == 1
    assert store.mark_result_calls == 1


def test_different_idempotency_key_cannot_reexecute():

    proposal = make_proposal(
        status=RemediationStatus.SUCCEEDED,
        idempotency_key="original-key-123",
    )

    executor = FakeExecutor()

    service, store = make_service(
        proposal,
        executor=executor,
    )

    with pytest.raises(PermissionError):
        service.execute(
            "rem-1",
            "operator",
            "different-key-123",
        )

    assert executor.calls == 0
    assert store.claim_calls == 0


def test_rerun_enters_verifying_after_accepted_submission():

    proposal = make_proposal(
        action=RemediationAction.RERUN_DEPLOYMENT,
    )

    executor = FakeExecutor(
        result={
            "action": "rerun_deployment",
            "status": "accepted",
            "http_status": 202,
            "deployment_id": "deployment-1",
        }
    )

    verifier = FakeVerifier(
        baseline={
            "baseline_attempt_number": 3,
            "baseline_attempt_id": "attempt-3",
        }
    )

    service, store = make_service(
        proposal,
        executor=executor,
        verifier=verifier,
    )

    result = service.execute(
        "rem-1",
        "operator",
        "rerun-key-123",
    )

    assert result.status == RemediationStatus.VERIFYING
    assert (
        result.execution_idempotency_key
        == "rerun-key-123"
    )

    assert verifier.snapshot_calls == 1
    assert executor.calls == 1
    assert store.mark_verifying_calls == 1
    assert store.mark_verified_calls == 0


def test_executor_failure_is_recorded_as_failed():

    proposal = make_proposal()

    executor = FakeExecutor(
        error=RuntimeError(
            "controlled executor failure"
        )
    )

    service, store = make_service(
        proposal,
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="controlled executor failure",
    ):
        service.execute(
            "rem-1",
            "operator",
            "failure-key-123",
        )

    assert store.proposal.status == (
        RemediationStatus.FAILED
    )

    assert store.proposal.error == (
        "controlled executor failure"
    )

    assert executor.calls == 1


def test_terminal_same_key_is_idempotent():

    proposal = make_proposal(
        status=RemediationStatus.SUCCEEDED,
        idempotency_key="terminal-key-123",
    )

    executor = FakeExecutor()

    service, store = make_service(
        proposal,
        executor=executor,
    )

    result = service.execute(
        "rem-1",
        "operator",
        "terminal-key-123",
    )

    assert result.status == (
        RemediationStatus.SUCCEEDED
    )

    assert executor.calls == 0
    assert store.claim_calls == 0


def test_verify_success_transitions_to_succeeded():

    proposal = make_proposal(
        action=RemediationAction.RERUN_DEPLOYMENT,
        status=RemediationStatus.VERIFYING,
        idempotency_key="verify-success-123",
    )

    proposal = proposal.model_copy(
        update={
            "verification_result": {
                "execution": {
                    "status": "accepted",
                    "http_status": 202,
                },
                "baseline": {
                    "baseline_attempt_number": 3,
                    "baseline_attempt_id": "attempt-3",
                },
            }
        }
    )

    verifier = FakeVerifier(
        verification={
            "verified": True,
            "status": "succeeded",
            "attempt_number": 4,
        }
    )

    service, store = make_service(
        proposal,
        verifier=verifier,
    )

    result = service.verify("rem-1")

    assert result.status == (
        RemediationStatus.SUCCEEDED
    )

    assert verifier.verify_calls == 1
    assert store.mark_verified_calls == 1
    assert result.error is None


def test_verify_failure_transitions_to_failed():

    proposal = make_proposal(
        action=RemediationAction.RERUN_DEPLOYMENT,
        status=RemediationStatus.VERIFYING,
        idempotency_key="verify-failure-123",
    )

    proposal = proposal.model_copy(
        update={
            "verification_result": {
                "execution": {
                    "status": "accepted",
                    "http_status": 202,
                },
                "baseline": {
                    "baseline_attempt_number": 3,
                    "baseline_attempt_id": "attempt-3",
                },
            }
        }
    )

    verifier = FakeVerifier(
        verification={
            "verified": False,
            "status": "failed",
            "attempt_number": 4,
            "error_message": (
                "deployment attempt failed"
            ),
        }
    )

    service, store = make_service(
        proposal,
        verifier=verifier,
    )

    result = service.verify("rem-1")

    assert result.status == (
        RemediationStatus.FAILED
    )

    assert verifier.verify_calls == 1
    assert store.mark_verified_calls == 1
    assert result.error == (
        "deployment attempt failed"
    )


def test_transient_verification_error_stays_verifying():

    proposal = make_proposal(
        action=RemediationAction.RERUN_DEPLOYMENT,
        status=RemediationStatus.VERIFYING,
        idempotency_key="verify-retry-123",
    )

    proposal = proposal.model_copy(
        update={
            "verification_result": {
                "execution": {
                    "status": "accepted",
                    "http_status": 202,
                },
                "baseline": {
                    "baseline_attempt_number": 3,
                    "baseline_attempt_id": "attempt-3",
                },
            }
        }
    )

    verifier = FakeVerifier(
        error=RemediationVerificationError(
            "deployment service temporarily unavailable"
        )
    )

    service, store = make_service(
        proposal,
        verifier=verifier,
    )

    result = service.verify("rem-1")

    assert result.status == (
        RemediationStatus.VERIFYING
    )

    assert verifier.verify_calls == 1
    assert store.mark_verified_calls == 0
    assert (
        store.record_verification_attempt_calls
        == 1
    )

    assert result.error == (
        "deployment service temporarily unavailable"
    )

    assert (
        result.verification_result[
            "last_verification"
        ]["verification"]["status"]
        == "verification_unavailable"
    )


def test_verify_terminal_proposal_is_idempotent():

    proposal = make_proposal(
        action=RemediationAction.RERUN_DEPLOYMENT,
        status=RemediationStatus.SUCCEEDED,
        idempotency_key="already-done-123",
    )

    verifier = FakeVerifier()

    service, store = make_service(
        proposal,
        verifier=verifier,
    )

    result = service.verify("rem-1")

    assert result.status == (
        RemediationStatus.SUCCEEDED
    )

    assert verifier.verify_calls == 0
    assert store.mark_verified_calls == 0
