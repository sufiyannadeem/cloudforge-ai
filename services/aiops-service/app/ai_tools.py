from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .deployment_client import DeploymentClient
from .prometheus_client import PrometheusClient
from .store import IncidentStore


@dataclass(frozen=True)
class AIToolResult:
    """
    Result returned by a read-only AI operational tool.

    Tool results are evidence, not instructions.
    """

    tool: str
    success: bool
    data: Any
    error: str | None = None


class AIReadOnlyTools:
    """
    Controlled read-only operational tools available to CloudForge AI.

    IMPORTANT:

    These tools must never:
      - mutate incidents
      - create deployments
      - execute deployments
      - modify Kubernetes
      - modify AWS resources
      - execute shell commands
      - execute arbitrary SQL

    They only retrieve operational evidence.
    """

    def __init__(
        self,
        *,
        incident_store: IncidentStore | None = None,
        deployment_client: DeploymentClient | None = None,
        prometheus_client: PrometheusClient | None = None,
    ) -> None:
        self.incident_store = (
            incident_store or IncidentStore()
        )

        self.deployment_client = (
            deployment_client or DeploymentClient()
        )

        self.prometheus = (
            prometheus_client or PrometheusClient()
        )

    def get_incident(
        self,
        incident_id: str,
    ) -> AIToolResult:
        """
        Read a single incident.
        """

        incident = self.incident_store.get_by_id(
            incident_id
        )

        if incident is None:
            return AIToolResult(
                tool="incident.get",
                success=False,
                data=None,
                error="Incident not found.",
            )

        return AIToolResult(
            tool="incident.get",
            success=True,
            data=incident.model_dump(
                mode="json"
            ),
        )

    def list_deployments(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> AIToolResult:
        """
        Read deployment history.
        """

        limit = max(
            1,
            min(limit, 100),
        )

        offset = max(
            0,
            offset,
        )

        deployments, error = (
            self.deployment_client.list_deployments(
                limit=limit,
                offset=offset,
            )
        )

        if error:
            return AIToolResult(
                tool="deployments.list",
                success=False,
                data=[],
                error=error,
            )

        data = [
            {
                "id": deployment.id,
                "project_id": deployment.project_id,
                "environment": deployment.environment,
                "image": deployment.image,
                "git_commit_sha": (
                    deployment.git_commit_sha
                ),
                "namespace": deployment.namespace,
                "status": deployment.status,
                "created_at": (
                    deployment.created_at.isoformat()
                ),
                "updated_at": (
                    deployment.updated_at.isoformat()
                ),
            }
            for deployment in deployments
        ]

        return AIToolResult(
            tool="deployments.list",
            success=True,
            data=data,
        )

    def get_service_observability(
        self,
        service: str,
    ) -> AIToolResult:
        """
        Read Prometheus operational telemetry.
        """

        service = service.strip()

        if not service:
            return AIToolResult(
                tool="observability.service",
                success=False,
                data=None,
                error="Service is required.",
            )

        context = (
            self.prometheus.collect_operational_context(
                service
            )
        )

        return AIToolResult(
            tool="observability.service",
            success=True,
            data=context,
        )

    def collect_incident_evidence(
        self,
        *,
        incident_id: str,
        service: str,
    ) -> list[AIToolResult]:
        """
        Collect the standard read-only evidence set for an incident.

        This is intentionally deterministic.

        The AI does not decide which arbitrary tools to execute.
        CloudForge decides which evidence sources are permitted.
        """

        return [
            self.get_incident(
                incident_id
            ),
            self.get_service_observability(
                service
            ),
            self.list_deployments(
                limit=100,
                offset=0,
            ),
        ]
