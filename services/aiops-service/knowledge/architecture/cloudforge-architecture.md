# CloudForge AI Architecture

## Platform

CloudForge AI is a production-oriented Platform Engineering, DevOps, SRE, Observability, and AIOps platform.

## Core services

The application contains:

- frontend
- project-service
- infrastructure-service
- deployment-service
- aiops-service

## Operational flow

Developer changes flow through source control and CI/CD before deployment.

Runtime telemetry is collected by the observability stack.

Incidents are generated from operational alerts.

AI-Ops collects deterministic evidence and can use an AI provider to produce additional analysis.

## AI safety architecture

The intended workflow is:

evidence
-> recommendation
-> policy and guardrails
-> human approval
-> controlled execution
-> verification
-> audit

AI is not an infrastructure execution authority.

## Infrastructure authority

Terraform is the infrastructure execution authority.

AWS and Kubernetes changes must use controlled workflows rather than direct AI execution.
