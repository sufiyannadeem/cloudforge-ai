from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .service_identity import deployment_identity, open_deployment

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

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(
                os.getenv(
                    "DEPLOYMENT_SERVICE_TIMEOUT_SECONDS",
                    "5",
                )
            )
        )

    def execute(
        self,
        *,
        action: RemediationAction,
        incident_id: str,
        target_deployment_id: str | None,
        actor: str,
        proposal_id: str | None = None,
        dispatch_token: str | None = None,
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

            if not proposal_id or not dispatch_token:
                raise PermissionError("verified deployment dispatch required")

            return self._rerun_deployment(
                target_deployment_id,
                incident_id,
                actor,
                proposal_id,
                dispatch_token,
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
        proposal_id: str,
        dispatch_token: str,
    ) -> dict:
        url = (
            f"{self.base_url}"
            f"/api/v1/deployments/{deployment_id}/remediation-run"
        )

        request = urllib.request.Request(
            url,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-CloudForge-Incident": incident_id,
                "X-CloudForge-Identity": deployment_identity(url, "POST"),
                "X-CloudForge-Proposal": proposal_id,
                "X-CloudForge-Dispatch": dispatch_token,
            },
            data=b"",
        )

        try:
            with open_deployment(
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
            raise RuntimeError(
                f"deployment remediation rejected with HTTP {exc.code}"
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
