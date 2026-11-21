"""Shared deterministic fixtures for read-only AI evidence tests; never production data."""
from dataclasses import dataclass
from datetime import datetime, timezone


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
