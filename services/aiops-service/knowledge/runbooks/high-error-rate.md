# High Error Rate Runbook

## Purpose

Investigate elevated application request errors.

## Initial checks

1. Confirm the affected service.
2. Check current request rate.
3. Check current error rate.
4. Check p95 latency.
5. Determine whether the service is currently available.
6. Review recent deployments.

## Evidence

Useful operational evidence includes:

- request rate
- error rate
- service availability
- p95 latency
- deployment status
- deployment timestamp
- container image
- Git commit SHA

## Investigation

Compare the incident timestamp with recent deployments.

A deployment occurring near an incident is a temporal correlation. It does not independently establish causation.

Review application logs and deployment status before assigning a root cause.

## Recovery

If a deployment is confirmed to be responsible through operational evidence and approved procedures, follow the deployment rollback procedure.

Do not perform an automatic rollback solely because a deployment occurred near the incident.

## Escalation

Escalate when:

- error rate remains elevated
- service availability is degraded
- multiple services are affected
- evidence is insufficient to establish a likely cause
