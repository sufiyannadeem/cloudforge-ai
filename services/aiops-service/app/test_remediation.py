from __future__ import annotations

from datetime import datetime, timezone

from .remediation_models import (
    PolicyDecision,
    RemediationAction,
)
from .remediation_policy import RemediationPolicy


def test_no_action_allowed():
    policy = RemediationPolicy()

    result = policy.evaluate(
        RemediationAction.NO_ACTION,
        incident_status="open",
        target_deployment_id=None,
    )

    assert result.decision == PolicyDecision.ALLOWED
    assert result.executable is True
    assert result.requires_human_approval is False


def test_acknowledge_allowed():
    policy = RemediationPolicy()

    result = policy.evaluate(
        RemediationAction.ACKNOWLEDGE_INCIDENT,
        incident_status="open",
        target_deployment_id=None,
    )

    assert result.decision == PolicyDecision.ALLOWED
    assert result.executable is True


def test_rerun_requires_approval():
    policy = RemediationPolicy()

    result = policy.evaluate(
        RemediationAction.RERUN_DEPLOYMENT,
        incident_status="open",
        target_deployment_id="deployment-123",
    )

    assert result.decision == PolicyDecision.REQUIRES_APPROVAL
    assert result.requires_human_approval is True
    assert result.executable is True


def test_rerun_without_target_is_blocked():
    policy = RemediationPolicy()

    result = policy.evaluate(
        RemediationAction.RERUN_DEPLOYMENT,
        incident_status="open",
        target_deployment_id=None,
    )

    assert result.decision == PolicyDecision.BLOCKED
    assert result.executable is False


def test_restart_is_blocked():
    policy = RemediationPolicy()

    result = policy.evaluate(
        RemediationAction.RESTART_DEPLOYMENT,
        incident_status="open",
        target_deployment_id="deployment-123",
    )

    assert result.decision == PolicyDecision.BLOCKED
    assert result.executable is False


def test_scale_is_blocked():
    policy = RemediationPolicy()

    result = policy.evaluate(
        RemediationAction.SCALE_DEPLOYMENT,
        incident_status="open",
        target_deployment_id="deployment-123",
    )

    assert result.decision == PolicyDecision.BLOCKED
    assert result.executable is False


def test_rollback_is_blocked():
    policy = RemediationPolicy()

    result = policy.evaluate(
        RemediationAction.ROLLBACK_DEPLOYMENT,
        incident_status="open",
        target_deployment_id="deployment-123",
    )

    assert result.decision == PolicyDecision.BLOCKED
    assert result.executable is False


if __name__ == "__main__":
    tests = [
        test_no_action_allowed,
        test_acknowledge_allowed,
        test_rerun_requires_approval,
        test_rerun_without_target_is_blocked,
        test_restart_is_blocked,
        test_scale_is_blocked,
        test_rollback_is_blocked,
    ]

    for test in tests:
        test()

    print("ALL DAY 5 REMEDIATION POLICY TESTS PASSED")
