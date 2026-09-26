from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import AIAnalysis, AnalysisConfidence


class AIResponsePayload(BaseModel):
    """
    Strict schema for the untrusted response returned by an AI provider.

    The provider is never allowed to directly construct the persisted
    AIAnalysis object. The response is validated first.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    model: str | None = None

    summary: str = Field(
        min_length=1,
        max_length=4000,
    )

    probable_cause: str = Field(
        min_length=1,
        max_length=4000,
    )

    root_cause_hints: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    recommended_actions: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    confidence: AnalysisConfidence

    assessment: str = Field(
        min_length=1,
        max_length=100,
    )

    evidence: dict[str, float | int | None] = Field(
        default_factory=dict,
    )

    evidence_findings: list[str] = Field(
        default_factory=list,
        max_length=50,
    )

    deployment_correlations: list[dict[str, object]] = Field(
        default_factory=list,
        max_length=100,
    )


class AIValidationResult(BaseModel):
    """
    Result returned by the AI guardrail pipeline.
    """

    valid: bool

    analysis: AIAnalysis | None = None

    error: str | None = None


class AIGuardrailValidator:
    """
    Validates untrusted AI output against deterministic evidence.

    Important principle:

        AI may interpret evidence.
        AI may not redefine evidence.

    Deterministic Prometheus observations and deployment correlations
    remain authoritative.
    """

    ALLOWED_ASSESSMENTS = {
        "alert_supported",
        "alert_not_currently_observed",
        "evidence_available",
        "insufficient_evidence",
    }

    REQUIRED_EVIDENCE_KEYS = {
        "service_up",
        "request_rate",
        "error_rate",
        "p95_latency_seconds",
        "requests_in_flight",
        "deployments_in_progress",
        "deployment_failures",
        "deployment_total",
    }

    MAX_TEXT_LENGTH = 4000

    def validate(
        self,
        content: str,
        fallback: AIAnalysis,
    ) -> AIValidationResult:
        """
        Validate an AI provider response.

        The fallback deterministic analysis is used as the authoritative
        evidence source.
        """

        try:
            payload = self._decode_json(content)

            validated = AIResponsePayload.model_validate(
                payload
            )

            self._validate_assessment(
                validated.assessment
            )

            self._validate_evidence(
                ai_evidence=validated.evidence,
                deterministic_evidence=fallback.evidence,
            )

            self._validate_deployment_correlations(
                ai_correlations=(
                    validated.deployment_correlations
                ),
                deterministic_correlations=(
                    fallback.deployment_correlations
                ),
            )

            self._validate_text(
                validated
            )

            analysis = AIAnalysis(
                status="ai_generated",
                provider="mock",
                model=validated.model,
                summary=validated.summary,
                probable_cause=validated.probable_cause,
                root_cause_hints=validated.root_cause_hints,
                recommended_actions=validated.recommended_actions,
                confidence=validated.confidence,
                assessment=validated.assessment,
                evidence=dict(
                    fallback.evidence
                ),
                evidence_findings=(
                    validated.evidence_findings
                ),
                deployment_correlations=list(
                    fallback.deployment_correlations
                ),
                generated_at=fallback.generated_at,
                error=None,
            )

            return AIValidationResult(
                valid=True,
                analysis=analysis,
                error=None,
            )

        except (
            ValidationError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            return AIValidationResult(
                valid=False,
                analysis=None,
                error=str(exc),
            )

    def _decode_json(
        self,
        content: str,
    ) -> dict[str, Any]:
        if not isinstance(content, str):
            raise TypeError(
                "AI response content must be a string."
            )

        normalized = content.strip()

        if not normalized:
            raise ValueError(
                "AI response is empty."
            )

        # Handle providers that wrap JSON in markdown fences.
        if normalized.startswith("```"):
            lines = normalized.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            normalized = "\n".join(lines).strip()

        payload = json.loads(normalized)

        if not isinstance(payload, dict):
            raise ValueError(
                "AI response must be a JSON object."
            )

        return payload

    def _validate_assessment(
        self,
        assessment: str,
    ) -> None:
        if assessment not in self.ALLOWED_ASSESSMENTS:
            raise ValueError(
                "Unsupported AI assessment: "
                f"{assessment!r}"
            )

    def _validate_evidence(
        self,
        ai_evidence: dict[str, float | int | None],
        deterministic_evidence: dict[
            str,
            float | int | None,
        ],
    ) -> None:
        """
        AI evidence is informational only.

        Every authoritative evidence value must remain identical to
        deterministic evidence.
        """

        missing_keys = (
            self.REQUIRED_EVIDENCE_KEYS
            - set(deterministic_evidence.keys())
        )

        if missing_keys:
            raise ValueError(
                "Deterministic evidence is missing required "
                f"fields: {sorted(missing_keys)}"
            )

        for key, expected in deterministic_evidence.items():
            if key not in ai_evidence:
                continue

            actual = ai_evidence[key]

            if expected is None:
                if actual is not None:
                    raise ValueError(
                        "AI attempted to invent evidence for "
                        f"{key}: expected null, got {actual!r}"
                    )

                continue

            if actual is None:
                raise ValueError(
                    "AI removed available evidence for "
                    f"{key}."
                )

            try:
                expected_float = float(expected)
                actual_float = float(actual)
            except (
                TypeError,
                ValueError,
            ):
                raise ValueError(
                    f"Invalid numeric evidence for {key}."
                )

            if abs(
                expected_float - actual_float
            ) > 1e-9:
                raise ValueError(
                    "AI attempted to modify deterministic "
                    f"evidence for {key}: expected "
                    f"{expected!r}, got {actual!r}"
                )

    def _validate_deployment_correlations(
        self,
        ai_correlations: list[dict[str, object]],
        deterministic_correlations: list[
            dict[str, object]
        ],
    ) -> None:
        """
        Deployment correlations are deterministic evidence.

        The AI cannot add, remove, reorder, or modify
        deterministic deployment correlations.

        Both sides are normalized before comparison because
        the AI response passes through Pydantic validation
        and may contain equivalent JSON values represented
        by different Python container types.
        """

        if not isinstance(
            ai_correlations,
            list,
        ):
            raise ValueError(
                "AI deployment correlations must be a list."
            )

        if not isinstance(
            deterministic_correlations,
            list,
        ):
            raise ValueError(
                "Deterministic deployment correlations "
                "must be a list."
            )

        def normalize(
            correlations: list[
                dict[str, object]
            ],
        ) -> list[dict[str, object]]:
            normalized: list[
                dict[str, object]
            ] = []

            for correlation in correlations:
                if not isinstance(
                    correlation,
                    dict,
                ):
                    raise ValueError(
                        "Each deployment correlation "
                        "must be an object."
                    )

                normalized.append(
                    {
                        str(key): value
                        for key, value
                        in correlation.items()
                    }
                )

            return normalized

        ai_normalized = normalize(
            ai_correlations
        )

        deterministic_normalized = normalize(
            deterministic_correlations
        )

        if ai_normalized != deterministic_normalized:
            raise ValueError(
                "AI deployment correlations do not match "
                "deterministic deployment evidence."
            )

        for correlation in deterministic_normalized:
            correlation_type = correlation.get(
                "correlation_type"
            )

            if (
                correlation_type
                == "temporal_deployment_correlation"
            ):
                explanation = str(
                    correlation.get(
                        "explanation",
                        "",
                    )
                ).lower()

                if (
                    "does not establish" not in explanation
                    or "causation" not in explanation
                ):
                    raise ValueError(
                        "Temporal deployment correlation "
                        "is missing explicit non-causation "
                        "language."
                    )

    def _validate_text(
        self,
        response: AIResponsePayload,
    ) -> None:
        fields = {
            "summary": response.summary,
            "probable_cause": response.probable_cause,
        }

        for name, value in fields.items():
            if len(value) > self.MAX_TEXT_LENGTH:
                raise ValueError(
                    f"AI field {name!r} exceeds the "
                    f"{self.MAX_TEXT_LENGTH} character limit."
                )

        for field_name, values in (
            (
                "root_cause_hints",
                response.root_cause_hints,
            ),
            (
                "recommended_actions",
                response.recommended_actions,
            ),
            (
                "evidence_findings",
                response.evidence_findings,
            ),
        ):
            for index, value in enumerate(values):
                if not isinstance(value, str):
                    raise ValueError(
                        f"{field_name}[{index}] must be a string."
                    )

                if not value.strip():
                    raise ValueError(
                        f"{field_name}[{index}] cannot be empty."
                    )

                if len(value) > self.MAX_TEXT_LENGTH:
                    raise ValueError(
                        f"{field_name}[{index}] exceeds the "
                        f"{self.MAX_TEXT_LENGTH} character limit."
                    )


ai_guardrail_validator = AIGuardrailValidator()
