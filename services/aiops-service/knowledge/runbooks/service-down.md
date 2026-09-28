# Service Down Runbook

## Purpose

Investigate a service that appears unavailable.

## Initial checks

Check:

- service availability
- request rate
- error rate
- p95 latency
- deployment status
- recent deployment activity

## Investigation

Determine whether the failure is:

- isolated to the service
- caused by a deployment
- caused by an upstream dependency
- caused by infrastructure
- insufficiently evidenced

A service-down signal alone does not establish root cause.

## Recovery

Follow the approved recovery procedure for the affected service.

AI analysis may recommend an action, but execution requires the established approval and remediation workflow.

## Escalation

Escalate immediately when production availability is materially degraded or evidence indicates a broader platform incident.
