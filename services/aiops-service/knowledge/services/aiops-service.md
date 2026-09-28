# AI-Ops Service

## Responsibility

The AI-Ops service provides incident intelligence, anomaly detection, evidence collection, AI-assisted analysis, guardrails, and controlled remediation workflows.

## Evidence sources

The service can use:

- incident records
- Prometheus operational telemetry
- deployment history
- deterministic anomaly analysis
- deployment correlations
- validated operational knowledge

## AI safety

AI-generated analysis is untrusted until validated by deterministic guardrails.

The AI must not:

- modify AWS infrastructure directly
- modify Kubernetes directly
- execute arbitrary shell commands
- execute arbitrary SQL
- bypass approval requirements

## Provider model

The AI provider layer supports configurable providers.

Local mock mode is available for development and testing.
