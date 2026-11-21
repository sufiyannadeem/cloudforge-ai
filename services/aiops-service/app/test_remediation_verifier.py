from __future__ import annotations

from collections import deque

import pytest

from .remediation_verifier import (
    DeploymentVerificationClient,
    RemediationVerificationTimeout,
)


def test_snapshot_returns_latest_attempt_number():
    responses = deque(
        [
            {
                "deployment_id": "deployment-1",
                "attempts": [
                    {
                        "id": "attempt-2",
                        "attempt_number": 2,
                        "status": "failed",
                    },
                    {
                        "id": "attempt-1",
                        "attempt_number": 1,
                        "status": "succeeded",
                    },
                ],
            }
        ]
    )

    verifier = DeploymentVerificationClient(
        fetch_json=lambda path: responses.popleft(),
        sleep=lambda _: None,
    )

    snapshot = verifier.snapshot(
        "deployment-1"
    )

    assert snapshot["baseline_attempt_number"] == 2
    assert snapshot["baseline_attempt_id"] == "attempt-2"


def test_verify_waits_for_new_attempt_then_succeeds():
    responses = deque(
        [
            {
                "status": "queued",
            },
            {
                "attempts": [
                    {
                        "id": "old",
                        "attempt_number": 3,
                        "status": "succeeded",
                    }
                ],
            },
            {
                "status": "running",
            },
            {
                "attempts": [
                    {
                        "id": "new",
                        "attempt_number": 4,
                        "status": "running",
                    }
                ],
            },
            {
                "status": "succeeded",
            },
            {
                "attempts": [
                    {
                        "id": "new",
                        "attempt_number": 4,
                        "status": "succeeded",
                    }
                ],
            },
        ]
    )

    verifier = DeploymentVerificationClient(
        fetch_json=lambda path: responses.popleft(),
        sleep=lambda _: None,
    )

    result = verifier.verify_rerun(
        "deployment-1",
        baseline_attempt_number=3,
    )

    assert result["verified"] is True
    assert result["verification"] == "succeeded"
    assert result["latest_attempt"]["attempt_number"] == 4


def test_verify_new_attempt_failure_is_not_success():
    responses = deque(
        [
            {
                "status": "failed",
            },
            {
                "attempts": [
                    {
                        "id": "new",
                        "attempt_number": 5,
                        "status": "failed",
                        "error_message": "deployment failed",
                    }
                ],
            },
        ]
    )

    verifier = DeploymentVerificationClient(
        fetch_json=lambda path: responses.popleft(),
        sleep=lambda _: None,
    )

    result = verifier.verify_rerun(
        "deployment-1",
        baseline_attempt_number=4,
    )

    assert result["verified"] is False
    assert result["verification"] == "failed"
    assert (
        result["error_message"]
        == "deployment failed"
    )


def test_verify_cancelled_attempt_is_failure():
    responses = deque(
        [
            {
                "status": "cancelled",
            },
            {
                "attempts": [
                    {
                        "id": "new",
                        "attempt_number": 7,
                        "status": "cancelled",
                    }
                ],
            },
        ]
    )

    verifier = DeploymentVerificationClient(
        fetch_json=lambda path: responses.popleft(),
        sleep=lambda _: None,
    )

    result = verifier.verify_rerun(
        "deployment-1",
        baseline_attempt_number=6,
    )

    assert result["verified"] is False
    assert result["verification"] == "failed"


def test_verify_timeout_does_not_claim_success():
    responses = deque(
        [
            {
                "status": "queued",
            },
            {
                "attempts": [
                    {
                        "id": "old",
                        "attempt_number": 10,
                        "status": "succeeded",
                    }
                ],
            },
        ]
        * 3
    )

    verifier = DeploymentVerificationClient(
        fetch_json=lambda path: responses.popleft(),
        verification_timeout_seconds=0,
        poll_interval_seconds=0,
        sleep=lambda _: None,
    )

    with pytest.raises(
        RemediationVerificationTimeout,
        match="verification timed out",
    ):
        verifier.verify_rerun(
            "deployment-1",
            baseline_attempt_number=10,
        )


def test_latest_attempt_ignores_older_attempts():
    responses = deque(
        [
            {
                "status": "running",
            },
            {
                "attempts": [
                    {
                        "id": "attempt-11",
                        "attempt_number": 11,
                        "status": "running",
                    },
                    {
                        "id": "attempt-12",
                        "attempt_number": 12,
                        "status": "succeeded",
                    },
                ],
            },
        ]
    )

    verifier = DeploymentVerificationClient(
        fetch_json=lambda path: responses.popleft(),
        sleep=lambda _: None,
    )

    result = verifier.verify_rerun(
        "deployment-1",
        baseline_attempt_number=10,
    )

    assert result["verified"] is True
    assert (
        result["latest_attempt"]["attempt_number"]
        == 12
    )
