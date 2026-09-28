from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.ai_evidence import AIEvidenceEnvelope
from app.ai_tools import AIReadOnlyTools


class FakeIncident:
    def model_dump(self, mode="json"):
        return {
            "id": "incident-1",
            "service": "deployment-service",
            "severity": "warning",
        }


class FakeIncidentStore:
    def get_by_id(self, incident_id):
        if incident_id == "incident-1":
            return FakeIncident()

        return None


@dataclass
class FakeDeployment:
    id: str
    project_id: str
    environment: str
    image: str
    git_commit_sha: str
    namespace: str
    status: str
    created_at: datetime
    updated_at: datetime


class FakeDeploymentClient:
    def list_deployments(
        self,
        limit=100,
        offset=0,
    ):
        deployment = FakeDeployment(
            id="deployment-1",
            project_id="project-1",
            environment="development",
            image="nginx:1.27-alpine",
            git_commit_sha="abcdef1234567",
            namespace="cloudforge-dev",
            status="succeeded",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        return [deployment], None


class FakePrometheusClient:
    def collect_operational_context(
        self,
        service,
    ):
        return {
            "service": service,
            "metrics": {
                "service_up": 1.0,
                "request_rate": 10.0,
                "error_rate": 0.01,
                "p95_latency_seconds": 0.120,
            },
            "errors": {},
        }


def test_incident_tool():
    tools = AIReadOnlyTools(
        incident_store=FakeIncidentStore(),
        deployment_client=FakeDeploymentClient(),
        prometheus_client=FakePrometheusClient(),
    )

    result = tools.get_incident(
        "incident-1"
    )

    assert result.success
    assert result.tool == "incident.get"
    assert result.data["id"] == "incident-1"


def test_missing_incident():
    tools = AIReadOnlyTools(
        incident_store=FakeIncidentStore(),
        deployment_client=FakeDeploymentClient(),
        prometheus_client=FakePrometheusClient(),
    )

    result = tools.get_incident(
        "does-not-exist"
    )

    assert not result.success
    assert result.error == "Incident not found."


def test_deployment_tool():
    tools = AIReadOnlyTools(
        incident_store=FakeIncidentStore(),
        deployment_client=FakeDeploymentClient(),
        prometheus_client=FakePrometheusClient(),
    )

    result = tools.list_deployments()

    assert result.success
    assert result.tool == "deployments.list"
    assert len(result.data) == 1
    assert result.data[0]["id"] == "deployment-1"


def test_observability_tool():
    tools = AIReadOnlyTools(
        incident_store=FakeIncidentStore(),
        deployment_client=FakeDeploymentClient(),
        prometheus_client=FakePrometheusClient(),
    )

    result = tools.get_service_observability(
        "deployment-service"
    )

    assert result.success
    assert result.tool == "observability.service"
    assert (
        result.data["metrics"]["service_up"]
        == 1.0
    )


def test_evidence_envelope():
    tools = AIReadOnlyTools(
        incident_store=FakeIncidentStore(),
        deployment_client=FakeDeploymentClient(),
        prometheus_client=FakePrometheusClient(),
    )

    results = tools.collect_incident_evidence(
        incident_id="incident-1",
        service="deployment-service",
    )

    envelope = AIEvidenceEnvelope(
        incident_id="incident-1"
    )

    for result in results:
        envelope.add(result)

    assert len(envelope.evidence) == 3
    assert len(
        envelope.successful_evidence()
    ) == 3

    prompt_context = (
        envelope.to_prompt_context()
    )

    assert (
        "CLOUDFORGE OPERATIONAL EVIDENCE"
        in prompt_context
    )

    assert "deployment-service" in prompt_context
    assert "deployment-1" in prompt_context


def run():
    print("========================================")
    print("AI READ-ONLY TOOL VALIDATION")
    print("========================================")

    test_incident_tool()
    print("INCIDENT TOOL: PASS")

    test_missing_incident()
    print("MISSING INCIDENT HANDLING: PASS")

    test_deployment_tool()
    print("DEPLOYMENT TOOL: PASS")

    test_observability_tool()
    print("OBSERVABILITY TOOL: PASS")

    test_evidence_envelope()
    print("EVIDENCE ENVELOPE: PASS")

    print()
    print("ALL AI TOOL TESTS PASSED")


if __name__ == "__main__":
    run()
