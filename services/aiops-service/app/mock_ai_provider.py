from __future__ import annotations

import json
import os
from typing import Any

from .ai_provider import AIProviderResult


class MockAIProvider:
    """
    Local AI provider used for development and integration testing.

    No external API calls are made.

    Supported modes:

        valid
        tampered
        invalid_json
        unsupported_assessment
        empty
    """

    name = "mock"

    def __init__(
        self,
        mode: str | None = None,
    ) -> None:
        self.mode = (
            mode
            or os.getenv(
                "AI_MOCK_MODE",
                "valid",
            )
        ).strip().lower()

    def analyze(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        del system_prompt

        if self.mode == "invalid_json":
            return AIProviderResult(
                status="success",
                provider="mock",
                model="cloudforge-mock-v1",
                content="{invalid-json",
                error=None,
            )

        if self.mode == "empty":
            return AIProviderResult(
                status="success",
                provider="mock",
                model="cloudforge-mock-v1",
                content="",
                error=None,
            )

        payload = self._build_payload(
            user_prompt
        )

        if self.mode == "tampered":
            payload["evidence"]["error_rate"] = 99.0

        elif self.mode == "unsupported_assessment":
            payload["assessment"] = (
                "root_cause_confirmed"
            )

        return AIProviderResult(
            status="success",
            provider="mock",
            model="cloudforge-mock-v1",
            content=json.dumps(
                payload,
                separators=(",", ":"),
            ),
            error=None,
        )

    def _build_payload(
        self,
        user_prompt: str,
    ) -> dict[str, Any]:
        """
        Build a response strictly from the supplied
        deterministic evidence.

        The mock provider does not generate independent
        telemetry.
        """

        try:
            normalized_prompt = user_prompt.strip()

            json_start = normalized_prompt.find(
                "{"
            )

            if json_start == -1:
                raise ValueError(
                    "No JSON payload found in AI prompt."
                )

            request, _ = json.JSONDecoder().raw_decode(
                normalized_prompt[json_start:]
            )

        except (
            json.JSONDecodeError,
            ValueError,
        ):
            request = {}

        deterministic = request.get(
            "deterministic_analysis",
            {},
        )

        operational_context = request.get(
            "operational_context",
            {},
        )

        deployment_correlations = request.get(
            "deployment_correlations",
            [],
        )

        evidence = dict(
            deterministic.get(
                "evidence",
                operational_context,
            )
            or {}
        )

        findings = list(
            deterministic.get(
                "evidence_findings",
                [],
            )
            or []
        )

        root_cause_hints = list(
            deterministic.get(
                "root_cause_hints",
                [],
            )
            or []
        )

        recommended_actions = list(
            deterministic.get(
                "recommended_actions",
                [],
            )
            or []
        )

        confidence = (
            deterministic.get(
                "confidence"
            )
            or "medium"
        )

        assessment = (
            deterministic.get(
                "assessment"
            )
            or "evidence_available"
        )

        probable_cause = (
            deterministic.get(
                "probable_cause"
            )
            or (
                "The available operational "
                "evidence does not establish "
                "a confirmed root cause."
            )
        )

        return {
            "model": "cloudforge-mock-v1",
            "summary": (
                "Mock AI analysis generated "
                "from CloudForge deterministic "
                "evidence. No independent "
                "telemetry was invented."
            ),
            "probable_cause": probable_cause,
            "root_cause_hints": root_cause_hints,
            "recommended_actions": (
                recommended_actions
            ),
            "confidence": confidence,
            "assessment": assessment,
            "evidence": evidence,
            "evidence_findings": findings,
            "deployment_correlations": (
                deployment_correlations
            ),
        }
