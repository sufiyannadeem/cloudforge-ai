# Deployment Service

## Responsibility

The deployment service manages deployment records and deployment lifecycle information.

## Operational evidence

The service exposes deployment information including:

- deployment ID
- project ID
- environment
- image
- Git commit SHA
- Kubernetes namespace
- deployment status
- creation timestamp
- update timestamp

## AI usage

CloudForge AI may use deployment records as read-only evidence.

The AI must not directly execute deployments or modify deployment state.
