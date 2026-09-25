from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class EnrichmentStatus(str, Enum):
    AI = "ai"
    FALLBACK = "fallback"
    DISABLED = "disabled"


class EnrichmentConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidencePack(BaseModel):
    incident_id: str
    service: str
    alert_name: str

    incident_summary: str
    deterministic_assessment: str | None = None

    evidence_findings: list[str] = Field(
        default_factory=list
    )

    operational_metrics: dict[
        str,
        float | int | None,
    ] = Field(
        default_factory=dict
    )

    anomaly_classification: str | None = None

    anomaly_metrics: list[dict[str, object]] = Field(
        default_factory=list
    )

    slo_classification: str | None = None

    slo_results: list[dict[str, object]] = Field(
        default_factory=list
    )

    deployment_correlations: list[
        dict[str, object]
    ] = Field(
        default_factory=list
    )


class AIEnrichment(BaseModel):
    status: EnrichmentStatus
    provider: str
    model: str | None = None

    summary: str
    probable_cause: str

    contributing_signals: list[str] = Field(
        default_factory=list
    )

    investigation_steps: list[str] = Field(
        default_factory=list
    )

    confidence: EnrichmentConfidence

    causality: str = (
        "Temporal or contextual correlation only; "
        "causality is not established."
    )

    evidence_used: list[str] = Field(
        default_factory=list
    )

    guardrail_warnings: list[str] = Field(
        default_factory=list
    )

    error: str | None = None

    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AIEnrichmentResponse(BaseModel):
    incident_id: str
    enrichment: AIEnrichment
    evidence: EvidencePack
