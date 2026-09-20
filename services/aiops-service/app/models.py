from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IncidentStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class IncidentSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertPayload(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    endsAt: str | None = None
    generatorURL: str | None = None


class AlertmanagerWebhook(BaseModel):
    receiver: str | None = None
    status: str = "firing"
    alerts: list[AlertPayload] = Field(default_factory=list)
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str | None = None
    version: str | None = None
    groupKey: str | None = None


class Incident(BaseModel):
    id: str
    fingerprint: str
    alert_name: str
    service: str
    severity: IncidentSeverity
    status: IncidentStatus
    summary: str
    probable_cause: str
    recommended_actions: list[str]
    labels: dict[str, str]
    annotations: dict[str, str]
    created_at: datetime
    updated_at: datetime
    alert_count: int = 1
    raw_alerts: list[dict[str, Any]] = Field(default_factory=list)


class IncidentListResponse(BaseModel):
    count: int
    incidents: list[Incident]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
