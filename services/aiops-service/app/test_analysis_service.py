from __future__ import annotations

from datetime import datetime, timezone

from app.ai_provider import AIProviderResult
from app.analysis_service import IncidentAnalysisService
from app.models import (
    AnalysisConfidence,
    Incident,
    IncidentImpact,
    IncidentSeverity,
    IncidentStatus,
)


class FakeIncidentStore:
    def __init__(self, incident: Incident) -> None:
        self.incident = incident
        self.saved_analysis = None

    def get_by_id(self, incident_id: str):
        if incident_id != self.incident.id:
            return None

        return self.incident

    def save_ai_analysis(self, incident_id: str, analysis):
        if incident_id != self.incident.id:
            return None

        self.saved_analysis = analysis

        return self.incident.model_copy(
            update={
                "ai_analysis": analysis,
            }
        )


class FakePrometheusClient:
    def collect_operational_context(self, service: str):
        assert service == "deployment-service"

        return {
            "metrics": {
                "service_up": 1.0,
                "request_rate": 0.1684,
                "error_rate": 0.0,
                "p95_latency": 0.00475,
                "requests_in_flight": 1.0,
                "deployments_in_progress": 0.0,
                "deployment_failures": 0.0,
                "deployment_total": 1.0,
            },
            "errors": {},
        }


class FakeDeploymentClient:
    def list_deployments(
        self,
        limit: int,
        offset: int,
    ):
        assert limit == 100
        assert offset == 0

        return (
            [
                {
                    "deployment_id": "deployment-1",
                    "environment": "development",
                    "status": "succeeded",
                    "image": "nginx:1.27-alpine",
                    "git_commit_sha": "abcdef1234567",
                    "namespace": "cloudforge-dev",
                    "created_at": (
                        "2026-09-20T18:36:40.037707+00:00"
                    ),
                    "updated_at": (
                        "2026-09-20T18:37:06.918847+00:00"
                    ),
                }
            ],
            None,
        )


class FakeDeploymentCorrelationEngine:
    def correlate(
        self,
        incident_time,
        deployments,
    ):
        return []


class FakeAIProvider:
    enabled = True

    def __init__(self) -> None:
        self.system_prompt = None
        self.user_prompt = None

    def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt

        return AIProviderResult(
            status="success",
            provider="mock",
            model="cloudforge-mock-v1",
            content="""{
                "model": "cloudforge-mock-v1",
                "summary": "The incident has supporting operational evidence.",
                "probable_cause": "Current telemetry provides evidence for the incident.",
                "root_cause_hints": [
                    "Review deployment timing."
                ],
                "recommended_actions": [
                    "Inspect service logs."
                ],
                "confidence": "medium",
                "assessment": "evidence_available",
                "evidence": {
                    "service_up": 1.0,
                    "request_rate": 0.1684,
                    "error_rate": 0.0,
                    "p95_latency_seconds": 0.00475,
                    "requests_in_flight": 1.0,
                    "deployments_in_progress": 0.0,
                    "deployment_failures": 0.0,
                    "deployment_total": 1.0
                },
                "evidence_findings": [
                    "Prometheus currently reports the service as healthy."
                ],
                "deployment_correlations": []
            }""",
            error=None,
        )


def build_incident() -> Incident:
    now = datetime.now(timezone.utc)

    return Incident(
        id="incident-test-1",
        fingerprint="fingerprint-test-1",
        alert_name="DeploymentServiceGenericAlert",
        service="deployment-service",
        severity=IncidentSeverity.WARNING,
        status=IncidentStatus.OPEN,
        impact=IncidentImpact.MEDIUM,
        confidence=AnalysisConfidence.MEDIUM,
        analysis_version="1.0",
        priority="P3",
        summary="Deployment service alert.",
        probable_cause="Current evidence is available.",
        root_cause_hints=[
            "Review deployment timing."
        ],
        recommended_actions=[
            "Inspect service logs."
        ],
        labels={
            "alertname": "DeploymentServiceGenericAlert",
            "service": "deployment-service",
        },
        annotations={
            "summary": "Deployment service alert."
        },
        created_at=now,
        updated_at=now,
        raw_alerts=[],
        ai_analysis=None,
    )


def test_end_to_end_ai_analysis() -> None:
    incident = build_incident()
    store = FakeIncidentStore(incident)

    provider = FakeAIProvider()

    service = IncidentAnalysisService(
        prometheus_client=FakePrometheusClient(),
        provider=provider,
        deployment_client=FakeDeploymentClient(),
        deployment_correlation_engine=(
            FakeDeploymentCorrelationEngine()
        ),
    )

    result = service.analyze_incident(
        incident_id=incident.id,
        incident_store=store,
        use_ai=True,
    )

    assert result is not None
    assert result.ai_analysis is not None

    assert store.saved_analysis is not None

    analysis = store.saved_analysis

    assert analysis.status == "ai_generated"
    assert analysis.provider == "mock"
    assert analysis.model == "cloudforge-mock-v1"

    assert analysis.assessment == "evidence_available"

    assert analysis.evidence["service_up"] == 1.0
    assert analysis.evidence["request_rate"] == 0.1684
    assert analysis.evidence["error_rate"] == 0.0
    assert analysis.evidence["p95_latency_seconds"] == 0.00475

    assert analysis.summary is not None
    assert analysis.probable_cause is not None

    assert provider.user_prompt is not None

    assert (
        "CLOUDFORGE OPERATIONAL KNOWLEDGE"
        in provider.user_prompt
    )

    assert "Source:" in provider.user_prompt

    assert (
        "deployment-service"
        in provider.user_prompt
    )

    assert (
        "operational knowledge"
        in provider.user_prompt.lower()
    )


def run() -> None:
    print("========================================")
    print("ANALYSIS SERVICE VALIDATION")
    print("========================================")

    test_end_to_end_ai_analysis()

    print("END-TO-END AI ANALYSIS: PASS")
    print()
    print("ALL ANALYSIS SERVICE TESTS PASSED")


if __name__ == "__main__":
    run()
