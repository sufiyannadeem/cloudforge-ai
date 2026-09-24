from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class DeploymentRecord:
    id: str
    project_id: str
    environment: str
    image: str
    git_commit_sha: str
    namespace: str
    status: str
    created_at: datetime
    updated_at: datetime


class DeploymentClient:
    """
    Lightweight client for the CloudForge deployment service.

    The AI-Ops service uses this client to collect deployment evidence
    around an incident timestamp.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv(
                "DEPLOYMENT_SERVICE_URL",
                "http://deployment-service:8082",
            )
        ).rstrip("/")

        self.timeout_seconds = timeout_seconds or float(
            os.getenv(
                "DEPLOYMENT_SERVICE_TIMEOUT_SECONDS",
                "5",
            )
        )

    def list_deployments(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DeploymentRecord], str | None]:
        """
        Fetch deployments from the deployment service.

        Returns:
            deployments, error
        """

        query = urllib.parse.urlencode(
            {
                "limit": limit,
                "offset": offset,
            }
        )

        url = (
            f"{self.base_url}"
            f"/api/v1/deployments?{query}"
        )

        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            return [], (
                f"deployment service returned HTTP "
                f"{exc.code}"
            )

        except urllib.error.URLError as exc:
            return [], (
                f"deployment service unavailable: "
                f"{exc.reason}"
            )

        except TimeoutError:
            return [], "deployment service request timed out"

        except json.JSONDecodeError:
            return [], "deployment service returned invalid JSON"

        except Exception as exc:
            return [], (
                f"deployment service request failed: {exc}"
            )

        deployments: list[DeploymentRecord] = []

        for item in payload.get("items", []):
            try:
                deployments.append(
                    DeploymentRecord(
                        id=str(item["id"]),
                        project_id=str(item["project_id"]),
                        environment=str(
                            item.get("environment", "")
                        ),
                        image=str(item.get("image", "")),
                        git_commit_sha=str(
                            item.get("git_commit_sha", "")
                        ),
                        namespace=str(
                            item.get("namespace", "")
                        ),
                        status=str(item.get("status", "")),
                        created_at=self._parse_datetime(
                            item["created_at"]
                        ),
                        updated_at=self._parse_datetime(
                            item["updated_at"]
                        ),
                    )
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

        return deployments, None

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        normalized = value.replace(
            "Z",
            "+00:00",
        )

        parsed = datetime.fromisoformat(normalized)

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(timezone.utc)
