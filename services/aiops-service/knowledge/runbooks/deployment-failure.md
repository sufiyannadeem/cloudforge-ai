# Deployment Failure Runbook

## Purpose

Investigate failed deployment attempts.

## Initial checks

Review:

- deployment status
- environment
- container image
- Git commit SHA
- namespace
- deployment creation time
- deployment update time

## Investigation

Determine whether the failure is:

- application-related
- image-related
- configuration-related
- infrastructure-related
- caused by insufficient evidence

Compare deployment activity with related incidents.

Temporal proximity is evidence for correlation, not proof of causation.

## Recovery

Use the approved deployment recovery or rollback procedure.

No deployment mutation should be executed directly by an AI model.

## Escalation

Escalate when repeated deployment failures occur or when production availability is affected.
