from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .deployment_client import DeploymentRecord


@dataclass
class DeploymentCorrelation:
    deployment_id: str
    environment: str
    status: str
    image: str
    git_commit_sha: str
    namespace: str

    deployment_created_at: datetime
    deployment_updated_at: datetime

    incident_time_difference_seconds: float

    correlation_type: str
    correlation_strength: str
    explanation: str


class DeploymentCorrelationEngine:
    """
    Correlates incidents with deployments using temporal proximity.

    This engine intentionally does NOT claim causation.

    A deployment occurring near an incident is treated as:
        temporal correlation

    rather than:
        confirmed root cause
    """

    def __init__(
        self,
        correlation_window_seconds: int = 15 * 60,
    ) -> None:
        self.correlation_window_seconds = (
            correlation_window_seconds
        )

    def correlate(
        self,
        incident_time: datetime,
        deployments: Iterable[DeploymentRecord],
    ) -> list[DeploymentCorrelation]:
        correlations: list[DeploymentCorrelation] = []

        for deployment in deployments:
            difference = abs(
                (
                    deployment.created_at
                    - incident_time
                ).total_seconds()
            )

            if (
                difference
                > self.correlation_window_seconds
            ):
                continue

            correlations.append(
                DeploymentCorrelation(
                    deployment_id=deployment.id,
                    environment=deployment.environment,
                    status=deployment.status,
                    image=deployment.image,
                    git_commit_sha=deployment.git_commit_sha,
                    namespace=deployment.namespace,
                    deployment_created_at=(
                        deployment.created_at
                    ),
                    deployment_updated_at=(
                        deployment.updated_at
                    ),
                    incident_time_difference_seconds=(
                        difference
                    ),
                    correlation_type=(
                        "temporal_deployment_correlation"
                    ),
                    correlation_strength=(
                        self._strength(difference)
                    ),
                    explanation=(
                        self._build_explanation(
                            deployment,
                            difference,
                        )
                    ),
                )
            )

        correlations.sort(
            key=lambda item: (
                item.incident_time_difference_seconds
            )
        )

        return correlations

    def _strength(
        self,
        difference_seconds: float,
    ) -> str:
        if difference_seconds <= 60:
            return "high"

        if difference_seconds <= 5 * 60:
            return "medium"

        return "low"

    @staticmethod
    def _build_explanation(
        deployment: DeploymentRecord,
        difference_seconds: float,
    ) -> str:
        minutes = difference_seconds / 60

        if minutes < 1:
            time_text = "less than 1 minute"
        else:
            time_text = f"{minutes:.1f} minutes"

        return (
            f"Deployment {deployment.id} occurred "
            f"{time_text} from the incident timestamp. "
            f"Environment={deployment.environment}, "
            f"status={deployment.status}, "
            f"image={deployment.image}, "
            f"git_commit_sha={deployment.git_commit_sha}. "
            f"This is a temporal correlation and does not "
            f"establish deployment causation."
        )
