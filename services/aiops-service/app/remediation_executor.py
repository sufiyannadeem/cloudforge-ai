from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .remediation_models import RemediationAction


class RemediationExecutor:

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

    def execute(
        self,
        *,
        action: RemediationAction,
        incident_id: str,
        target_deployment_id: str | None,
        actor: str,
    ) -> dict:

        if action == RemediationAction.NO_ACTION:
            return {
                "action": action.value,
                "status": "succeeded",
                "message": "No production action was requested.",
                "actor": actor,
            }

        if action == RemediationAction.RERUN_DEPLOYMENT:
            if not target_deployment_id:
                raise ValueError(
                    "target_deployment_id is required"
                )

            return self._rerun_deployment(
                target_deployment_id,
                incident_id,
                actor,
            )

        if action == RemediationAction.ACKNOWLEDGE_INCIDENT:
            return {
                "action": action.value,
                "status": "requires_incident_store",
                "message": (
                    "Incident acknowledgement is handled by "
                    "the AIOps incident store."
                ),
                "actor": actor,
            }

        raise PermissionError(
            f"remediation action '{action.value}' is not executable "
            "by the current controlled executor"
        )

    def _rerun_deployment(
        self,
        deployment_id: str,
        incident_id: str,
        actor: str,
    ) -> dict:

        url = (
            f"{self.base_url}"
            f"/api/v1/deployments/{deployment_id}/run"
        )

        request = urllib.request.Request(
            url,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-CloudForge-Actor": actor,
                "X-CloudForge-Incident": incident_id,
                "X-CloudForge-Remediation": "human-approved",
            },
            data=b"",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")

                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {
                        "raw_response": raw,
                    }

                return {
                    "action": RemediationAction.RERUN_DEPLOYMENT.value,
                    "status": "accepted",
                    "http_status": response.status,
                    "deployment_id": deployment_id,
                    "response": payload,
                    "actor": actor,
                }

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")

            raise RuntimeError(
                f"deployment rerun rejected with HTTP "
                f"{exc.code}: {body}"
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"deployment service unavailable: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise RuntimeError(
                "deployment rerun request timed out"
            ) from exc


remediation_executor = RemediationExecutor()
