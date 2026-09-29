from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable


class RemediationVerificationError(RuntimeError):
    pass


class RemediationVerificationTimeout(
    RemediationVerificationError
):
    pass


class DeploymentVerificationClient:
    """
    Verifies a queued deployment rerun using the existing
    deployment-service deployment and attempt APIs.

    A rerun is considered verified only after a NEW deployment
    attempt appears beyond the baseline attempt number captured
    before the rerun was submitted.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        verification_timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
        fetch_json: Callable[[str], dict] | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
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

        self.verification_timeout_seconds = (
            verification_timeout_seconds
            if verification_timeout_seconds is not None
            else float(
                os.getenv(
                    "DEPLOYMENT_VERIFICATION_TIMEOUT_SECONDS",
                    "120",
                )
            )
        )

        self.poll_interval_seconds = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else float(
                os.getenv(
                    "DEPLOYMENT_VERIFICATION_POLL_INTERVAL_SECONDS",
                    "2",
                )
            )
        )

        self._fetch_json = fetch_json or self._http_get_json
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic

    def snapshot(
        self,
        deployment_id: str,
    ) -> dict:
        """
        Capture the latest attempt before submitting the rerun.
        """

        payload = self._fetch_json(
            f"/api/v1/deployments/{deployment_id}/attempts"
        )

        attempts = self._attempts(payload)

        latest = self._latest_attempt(attempts)

        return {
            "deployment_id": deployment_id,
            "baseline_attempt_number": (
                latest.get("attempt_number", 0)
                if latest
                else 0
            ),
            "baseline_attempt_id": (
                latest.get("id")
                if latest
                else None
            ),
            "captured_at": self._now(),
        }

    def verify_rerun(
        self,
        deployment_id: str,
        baseline_attempt_number: int,
    ) -> dict:
        """
        Wait for an attempt newer than baseline_attempt_number,
        then verify its terminal result.
        """

        started = self._clock()
        last_observation: dict = {}

        while (
            self._clock() - started
            <= self.verification_timeout_seconds
        ):
            deployment = self._fetch_json(
                f"/api/v1/deployments/{deployment_id}"
            )

            attempts_payload = self._fetch_json(
                f"/api/v1/deployments/{deployment_id}/attempts"
            )

            attempts = self._attempts(attempts_payload)

            new_attempts = [
                attempt
                for attempt in attempts
                if int(
                    attempt.get("attempt_number", 0)
                ) > baseline_attempt_number
            ]

            latest_new_attempt = self._latest_attempt(
                new_attempts
            )

            last_observation = {
                "deployment_id": deployment_id,
                "deployment_status": deployment.get(
                    "status"
                ),
                "baseline_attempt_number": (
                    baseline_attempt_number
                ),
                "latest_attempt": latest_new_attempt,
                "observed_at": self._now(),
            }

            # The important race protection:
            # never treat the old deployment state as the
            # result of the newly requested rerun.
            if latest_new_attempt is None:
                self._sleep(self.poll_interval_seconds)
                continue

            attempt_status = str(
                latest_new_attempt.get("status", "")
            ).lower()

            if attempt_status == "succeeded":
                return {
                    **last_observation,
                    "verification": "succeeded",
                    "verified": True,
                }

            if attempt_status in {
                "failed",
                "cancelled",
            }:
                return {
                    **last_observation,
                    "verification": "failed",
                    "verified": False,
                    "error_message": (
                        latest_new_attempt.get(
                            "error_message"
                        )
                    ),
                }

            self._sleep(self.poll_interval_seconds)

        raise RemediationVerificationTimeout(
            "deployment rerun verification timed out "
            f"after {self.verification_timeout_seconds:g}s; "
            "execution outcome is unknown"
        )

    @staticmethod
    def _attempts(payload: dict) -> list[dict]:
        attempts = payload.get("attempts", [])

        if not isinstance(attempts, list):
            raise RemediationVerificationError(
                "deployment attempts response is invalid"
            )

        return [
            attempt
            for attempt in attempts
            if isinstance(attempt, dict)
        ]

    @staticmethod
    def _latest_attempt(
        attempts: list[dict],
    ) -> dict | None:
        if not attempts:
            return None

        return max(
            attempts,
            key=lambda attempt: int(
                attempt.get("attempt_number", 0)
            ),
        )

    def _http_get_json(self, path: str) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
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
                raw = response.read().decode("utf-8")

                payload = json.loads(raw)

                if not isinstance(payload, dict):
                    raise RemediationVerificationError(
                        "deployment-service returned "
                        "a non-object JSON response"
                    )

                return payload

        except urllib.error.HTTPError as exc:
            body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RemediationVerificationError(
                "deployment verification request failed "
                f"with HTTP {exc.code}: {body}"
            ) from exc

        except urllib.error.URLError as exc:
            raise RemediationVerificationError(
                "deployment service unavailable during "
                f"verification: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise RemediationVerificationError(
                "deployment verification request timed out"
            ) from exc

        except json.JSONDecodeError as exc:
            raise RemediationVerificationError(
                "deployment-service returned invalid JSON"
            ) from exc

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()


remediation_verifier = DeploymentVerificationClient()
