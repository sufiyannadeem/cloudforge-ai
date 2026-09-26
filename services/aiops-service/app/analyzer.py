
import hashlib

from .models import (
    AlertPayload,
    AnalysisConfidence,
    Incident,
    IncidentImpact,
    IncidentSeverity,
    IncidentStatus,
    utc_now,
)


ANALYSIS_VERSION = "1.2"


def calculate_fingerprint(alert: AlertPayload) -> str:
    alert_name = alert.labels.get(
        "alertname",
        "UnknownAlert",
    )

    service = alert.labels.get(
        "service",
        "unknown-service",
    )

    raw_value = f"{alert_name}:{service}"

    return hashlib.sha256(
        raw_value.encode()
    ).hexdigest()[:16]


def determine_severity(
    alert: AlertPayload,
) -> IncidentSeverity:
    severity = alert.labels.get(
        "severity",
        "info",
    ).lower()

    if severity == "critical":
        return IncidentSeverity.CRITICAL

    if severity == "warning":
        return IncidentSeverity.WARNING

    return IncidentSeverity.INFO


def determine_impact(
    alert: AlertPayload,
) -> IncidentImpact:
    alert_name = alert.labels.get(
        "alertname",
        "UnknownAlert",
    )

    severity = determine_severity(alert)

    if alert_name == "DeploymentServiceDown":
        return IncidentImpact.CRITICAL

    if alert_name == "DeploymentServiceHighErrorRate":
        return IncidentImpact.HIGH

    if alert_name == "DeploymentServiceHighP95Latency":
        return IncidentImpact.MEDIUM

    if severity == IncidentSeverity.CRITICAL:
        return IncidentImpact.HIGH

    if severity == IncidentSeverity.WARNING:
        return IncidentImpact.MEDIUM

    return IncidentImpact.LOW


def determine_confidence(
    alert: AlertPayload,
) -> AnalysisConfidence:
    alert_name = alert.labels.get(
        "alertname",
        "UnknownAlert",
    )

    known_alerts = {
        "DeploymentServiceDown",
        "DeploymentServiceHighErrorRate",
        "DeploymentServiceHighP95Latency",
    }

    if alert_name in known_alerts:
        return AnalysisConfidence.HIGH

    return AnalysisConfidence.LOW


def determine_priority(
    alert: AlertPayload,
) -> str:
    """
    Assign an operational priority based on alert type
    and severity.

    P1: Critical service outage
    P2: Significant reliability or performance degradation
    P3: Warning-level issue
    P4: Informational or unknown issue
    """

    alert_name = alert.labels.get(
        "alertname",
        "UnknownAlert",
    )

    severity = determine_severity(alert)

    if alert_name == "DeploymentServiceDown":
        return "P1"

    if alert_name in {
        "DeploymentServiceHighErrorRate",
        "DeploymentServiceHighP95Latency",
    }:
        return "P2"

    if severity == IncidentSeverity.CRITICAL:
        return "P2"

    if severity == IncidentSeverity.WARNING:
        return "P3"

    return "P4"


def determine_root_cause_hints(
    alert: AlertPayload,
) -> list[str]:
    """
    Generate structured investigation hints.

    These are hypotheses for investigation, not confirmed
    root-cause findings.
    """

    alert_name = alert.labels.get(
        "alertname",
        "UnknownAlert",
    )

    if alert_name == "DeploymentServiceDown":
        return [
            "Deployment-service container may have stopped.",
            "Application process may have crashed.",
            "Health endpoint may be failing.",
            "Database connectivity may be unavailable.",
            "Prometheus may be unable to reach the service.",
            "Container or host resource exhaustion may be present.",
        ]

    if alert_name == "DeploymentServiceHighErrorRate":
        return [
            "Application may be returning HTTP 5xx responses.",
            "Database queries or connections may be failing.",
            "Recent application changes may have introduced errors.",
            "Downstream service dependencies may be unavailable.",
            "Invalid or unexpected request payloads may be triggering failures.",
        ]

    if alert_name == "DeploymentServiceHighP95Latency":
        return [
            "Database queries may be slow.",
            "Application may be experiencing CPU pressure.",
            "Application may be experiencing memory pressure.",
            "Long-running deployment operations may be blocking requests.",
            "Downstream dependencies may be responding slowly.",
        ]

    severity = determine_severity(alert)

    if severity == IncidentSeverity.CRITICAL:
        return [
            "Critical alert requires immediate investigation.",
            "Inspect service logs and related metrics.",
            "Check recent infrastructure or application changes.",
        ]

    if severity == IncidentSeverity.WARNING:
        return [
            "Review the alert labels and annotations.",
            "Inspect related Prometheus metrics.",
            "Check recent configuration changes.",
        ]

    return [
        "No specialized root-cause rule exists.",
        "Inspect alert labels and annotations.",
        "Review related service logs and metrics.",
    ]


def analyze_alert(alert: AlertPayload) -> Incident:
    alert_name = alert.labels.get(
        "alertname",
        "UnknownAlert",
    )

    service = alert.labels.get(
        "service",
        "unknown-service",
    )

    alert_status = alert.status.lower()

    severity = determine_severity(alert)
    impact = determine_impact(alert)
    confidence = determine_confidence(alert)
    priority = determine_priority(alert)
    root_cause_hints = determine_root_cause_hints(alert)

    if alert_status == "resolved":
        incident_status = IncidentStatus.RESOLVED
    else:
        incident_status = IncidentStatus.OPEN

    if alert_name == "DeploymentServiceDown":
        probable_cause = (
            "The deployment service may be unavailable, "
            "unhealthy, or unreachable by Prometheus."
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
            "The deployment service is returning an "
            "elevated number of HTTP 5xx responses."
        )

        recommended_actions = [
            "Inspect deployment-service logs for server errors.",
            "Check database availability.",
            "Review recent deployments and code changes.",
            "Inspect HTTP status metrics.",
        ]

    elif alert_name == "DeploymentServiceHighP95Latency":
        probable_cause = (
            "The deployment service is experiencing "
            "elevated 95th-percentile request latency."
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
        f"with {severity.value} severity, "
        f"{impact.value} impact, and "
        f"{priority} priority."
    )

    timestamp = utc_now()

    return Incident(
        id=f"inc-{timestamp.strftime('%Y%m%d%H%M%S%f')}",
        fingerprint=calculate_fingerprint(alert),
        alert_name=alert_name,
        service=service,
        severity=severity,
        status=incident_status,
        impact=impact,
        confidence=confidence,
        analysis_version=ANALYSIS_VERSION,
        priority=priority,
        summary=summary,
        probable_cause=probable_cause,
        root_cause_hints=root_cause_hints,
        recommended_actions=recommended_actions,
        labels=alert.labels,
        annotations=alert.annotations,
        created_at=timestamp,
        updated_at=timestamp,
        raw_alerts=[alert.model_dump()],
    )
