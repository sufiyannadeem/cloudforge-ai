from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SLOStatus(str, Enum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    INSUFFICIENT_DATA = "insufficient_data"


class SLOType(str, Enum):
    AVAILABILITY = "availability"
    ERROR_RATE = "error_rate"
    LATENCY = "latency"


class SLODefinition(BaseModel):
    name: str
    description: str
    service: str
    type: SLOType
    target: float
    window: str
    latency_threshold_ms: float | None = None


class SLOResult(BaseModel):
    name: str
    description: str
    service: str
    type: SLOType

    target: float
    window: str

    observed_value: float | None = None
    compliance: float | None = None

    error_budget_total: float | None = None
    error_budget_consumed: float | None = None
    error_budget_remaining: float | None = None

    burn_rate: float | None = None

    status: SLOStatus
    sufficient_data: bool

    latency_threshold_ms: float | None = None

    observed_at: datetime


class SLOSummary(BaseModel):
    service: str
    window: str
    overall_status: SLOStatus
    slo_count: int
    healthy_count: int
    at_risk_count: int
    breached_count: int
    insufficient_data_count: int
    slos: list[SLOResult] = Field(default_factory=list)
    generated_at: datetime
