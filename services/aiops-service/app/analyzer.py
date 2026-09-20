import hashlib
from typing import Any

from .models import (
    AlertPayload,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    utc_now,
)


def calculate_fingerprint(alert: AlertPayload) -> str:
    alert_name = alert.labels.get("alertname", "UnknownAlert")
    service = alert.labels.get("service", "unknown-service")

    raw_value = f"{alert_name}:{service}"
    return hashlib.sha256(raw_value.encode()).hexdigest()[:16]


def determine_severity(alert: AlertPayload) -> IncidentSeverity:
    severity = alert.labels.get("severity", "info").lower()

    if severity == "critical":
        return IncidentSeverity.CRITICAL

    if severity == "warning":
        return IncidentSeverity.WARNING

    return IncidentSeverity.INFO


def analyze_alert(alert: AlertPayload) -> Incident:
    alert_name = alert.labels.get("alertname", "UnknownAlert")
    service = alert.labels.get("service", "unknown-service")
    alert_status = alert.status.lower()

    severity = determine_severity(alert)

    if alert_status == "resolved":
        incident_status = IncidentStatus.RESOLVED
    else:
        incident_status = IncidentStatus.OPEN

    if alert_name == "DeploymentServiceDown":
        probable_cause = (
            "The deployment service may be unavailable, unhealthy, "
            "or unreachable by Prometheus."
        )

        recommended_actions = [
            "Check deployment-service container status.",
            "Check deployment-service application logs.",
            "Verify the /health endpoint.",
            "Check database connectivity.",
            "Verify Prometheus target health.",
        ]

    elif alert_name == "DeploymentServiceHighErrorRate":
        probable_cause = (
            "The deployment service is returning an elevated number "
            "of HTTP 5xx responses."
        )

        recommended_actions = [
            "Inspect deployment-service logs for server errors.",
            "Check database availability.",
            "Review recent deployments and code changes.",
            "Inspect HTTP status metrics.",
        ]

    elif alert_name == "DeploymentServiceHighP95Latency":
        probable_cause = (
            "The deployment service is experiencing elevated "
            "95th-percentile request latency."
        )

        recommended_actions = [
            "Check request latency metrics.",
            "Inspect database query performance.",
            "Review CPU and memory usage.",
            "Check for long-running requests.",
        ]

    else:
        probable_cause = (
            "No specialized rule exists for this alert. "
            "Additional metrics and logs are required."
        )

        recommended_actions = [
            "Inspect the alert labels and annotations.",
            "Review related Prometheus metrics.",
            "Check service logs.",
            "Investigate recent infrastructure changes.",
        ]

    summary = (
        f"{alert_name} detected for {service} "
        f"with {severity.value} severity."
    )

    timestamp = utc_now()

    return Incident(
        id=f"inc-{timestamp.strftime('%Y%m%d%H%M%S%f')}",
        fingerprint=calculate_fingerprint(alert),
        alert_name=alert_name,
        service=service,
        severity=severity,
        status=incident_status,
        summary=summary,
        probable_cause=probable_cause,
        recommended_actions=recommended_actions,
        labels=alert.labels,
        annotations=alert.annotations,
        created_at=timestamp,
        updated_at=timestamp,
        raw_alerts=[alert.model_dump()],
    )
