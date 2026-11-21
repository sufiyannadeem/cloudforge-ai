# High Latency Runbook

## Purpose

Investigate elevated request latency.

## Initial checks

Check:

- p95 latency
- request rate
- error rate
- service availability
- active deployments

## Investigation

Determine whether latency is isolated to one service or affects multiple services.

Compare the incident timestamp with deployment activity.

Review service-level telemetry before concluding that a deployment caused the latency increase.

## Evidence requirements

A latency assessment should identify:

- observed p95 latency
- observation window
- affected service
- request volume
- error rate
- relevant deployment activity

## Recovery

Use the established service recovery procedure.

Do not execute infrastructure or deployment changes solely from an AI recommendation.

## Escalation

Escalate when:

- latency breaches the applicable SLO
- latency continues to increase
- multiple services are affected
- sufficient evidence is unavailable
