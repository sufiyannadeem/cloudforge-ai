from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class AnomalyClassification(str, Enum):
    NORMAL = "normal"
    ANOMALY = "anomaly"
    CRITICAL = "critical"
    INSUFFICIENT_DATA = "insufficient_data"


class AnomalyDirection(str, Enum):
    STABLE = "stable"
    INCREASE = "increase"
    DECREASE = "decrease"


class AnomalyMetric(BaseModel):
    name: str
    display_name: str
    unit: str

    current_value: float | None = None
    baseline_value: float | None = None

    standard_deviation: float | None = None
    z_score: float | None = None

    deviation_percent: float | None = None

    direction: AnomalyDirection = AnomalyDirection.STABLE
    classification: AnomalyClassification

    evidence: list[str] = Field(default_factory=list)

    sample_count: int = 0

    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AnomalySummary(BaseModel):
    service: str

    window_minutes: int
    step_seconds: int

    overall_classification: AnomalyClassification

    normal_count: int
    anomaly_count: int
    critical_count: int
    insufficient_data_count: int

    metrics: list[AnomalyMetric]

    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
