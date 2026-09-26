from __future__ import annotations

import re

from .ai_enrichment_models import (
    AIEnrichment,
    EvidencePack,
)


class AIEnrichmentGuardrailError(ValueError):
    """Raised when AI enrichment violates evidence guardrails."""


class AIEnrichmentGuardrails:
    """
    Validates AI-generated enrichment against the deterministic
    evidence supplied to the enrichment pipeline.

    AI is allowed to interpret evidence.

    AI is not allowed to:
      - invent telemetry
      - claim confirmed causality
      - claim unsupported high confidence
      - reference evidence that was not supplied
    """

    CAUSAL_PATTERNS = (
        r"\bcaused by\b",
        r"\bcaused the\b",
        r"\bis the cause\b",
        r"\bdefinitively caused\b",
        r"\broot cause (?:is|was)\b",
        r"\b(?:is|was) the root cause\b",
        r"\broot cause has been (?:confirmed|identified)\b",
        r"\bconfirmed as the root cause\b",
    )

    MAX_SUMMARY_LENGTH = 500
    MAX_PROBABLE_CAUSE_LENGTH = 700
    MAX_LIST_ITEMS = 8
    MAX_ITEM_LENGTH = 500

    def validate(
        self,
        enrichment: AIEnrichment,
        evidence: EvidencePack,
    ) -> AIEnrichment:
        self._validate_lengths(enrichment)
        self._validate_confidence(
            enrichment,
            evidence,
        )
        self._validate_causality(enrichment)
        self._validate_evidence_claims(
            enrichment,
            evidence,
        )
        self._validate_status(enrichment)

        return enrichment

    @staticmethod
    def _validate_status(
        enrichment: AIEnrichment,
    ) -> None:
        if enrichment.status != "ai":
            raise AIEnrichmentGuardrailError(
                "Only validated AI enrichment may pass "
                "through the AI guardrail."
            )

    def _validate_lengths(
        self,
        enrichment: AIEnrichment,
    ) -> None:
        if len(enrichment.summary) > self.MAX_SUMMARY_LENGTH:
            raise AIEnrichmentGuardrailError(
                "AI summary exceeds the maximum allowed length."
            )

        if (
            len(enrichment.probable_cause)
            > self.MAX_PROBABLE_CAUSE_LENGTH
        ):
            raise AIEnrichmentGuardrailError(
                "AI probable cause exceeds the maximum allowed length."
            )

        fields = (
            "contributing_signals",
            "investigation_steps",
            "evidence_used",
        )

        for field_name in fields:
            values = getattr(
                enrichment,
                field_name,
            )

            if len(values) > self.MAX_LIST_ITEMS:
                raise AIEnrichmentGuardrailError(
                    f"AI field '{field_name}' contains too many items."
                )

            for value in values:
                if len(value) > self.MAX_ITEM_LENGTH:
                    raise AIEnrichmentGuardrailError(
                        f"AI field '{field_name}' contains "
                        "an item exceeding the maximum length."
                    )

    def _validate_confidence(
        self,
        enrichment: AIEnrichment,
        evidence: EvidencePack,
    ) -> None:
        has_evidence = bool(
            evidence.evidence_findings
            or evidence.anomaly_metrics
            or evidence.slo_results
            or evidence.deployment_correlations
            or evidence.operational_metrics
        )

        if (
            not has_evidence
            and enrichment.confidence
            == "high"
        ):
            raise AIEnrichmentGuardrailError(
                "High-confidence AI output requires supporting evidence."
            )

    def _validate_causality(
        self,
        enrichment: AIEnrichment,
    ) -> None:
        text = " ".join(
            [
                enrichment.summary,
                enrichment.probable_cause,
                enrichment.causality,
                *enrichment.contributing_signals,
            ]
        ).lower()

        for pattern in self.CAUSAL_PATTERNS:
            if re.search(pattern, text):
                raise AIEnrichmentGuardrailError(
                    "AI output makes an unsupported causal claim."
                )

    def _validate_evidence_claims(
        self,
        enrichment: AIEnrichment,
        evidence: EvidencePack,
    ) -> None:
        allowed_text = self._build_evidence_text(
            evidence
        )

        for claim in enrichment.evidence_used:
            normalized = claim.strip().lower()

            if not normalized:
                raise AIEnrichmentGuardrailError(
                    "AI evidence references cannot be empty."
                )

            if not self._claim_has_support(
                normalized,
                allowed_text,
            ):
                raise AIEnrichmentGuardrailError(
                    "AI referenced evidence that was not "
                    "present in the supplied evidence pack."
                )

    @staticmethod
    def _build_evidence_text(
        evidence: EvidencePack,
    ) -> str:
        parts = [
            evidence.incident_summary,
            evidence.deterministic_assessment or "",
            *evidence.evidence_findings,
        ]

        for key, value in (
            evidence.operational_metrics.items()
        ):
            parts.append(
                f"{key} {value}"
            )

        parts.append(
            f"anomaly classification "
            f"{evidence.anomaly_classification}"
        )

        parts.append(
            f"slo classification "
            f"{evidence.slo_classification}"
        )

        for metric in evidence.anomaly_metrics:
            parts.append(str(metric))

        for result in evidence.slo_results:
            parts.append(str(result))

        for deployment in (
            evidence.deployment_correlations
        ):
            parts.append(str(deployment))

        return " ".join(parts).lower()

    @staticmethod
    def _claim_has_support(
        claim: str,
        allowed_text: str,
    ) -> bool:
        if claim in allowed_text:
            return True

        tokens = {
            token
            for token in re.findall(
                r"[a-z0-9_.%-]+",
                claim,
            )
            if len(token) >= 4
        }

        if not tokens:
            return False

        matches = sum(
            token in allowed_text
            for token in tokens
        )

        return matches >= max(
            1,
            min(3, len(tokens)),
        )


ai_enrichment_guardrails = AIEnrichmentGuardrails()
