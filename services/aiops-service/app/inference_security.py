"""Fail-closed inference boundary. Never accepts operational free text."""
from __future__ import annotations

import json
import os

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class DisclosureEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # Fixed vocabulary prevents credentials, logs, identifiers and instructions escaping.
    signal: Literal["latency", "error_rate", "availability", "deployment_correlation"]
    state: Literal["healthy", "degraded", "unknown"]


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    assessment: Literal["healthy", "degraded", "insufficient_evidence"]
    confidence: Literal["low", "medium"]
    citations: list[int] = Field(min_length=1, max_length=8)


def approved_payload(raw: str) -> dict:
    """Legacy prompts are deliberately rejected; authorization precedes disclosure."""
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"evidence"}:
        raise ValueError("Unapproved disclosure contract")
    evidence = value["evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 8:
        raise ValueError("Evidence bounds")
    clean = [DisclosureEvidence.model_validate(item).model_dump() for item in evidence]
    if len({item["signal"] for item in clean}) != len(clean):
        raise ValueError("Duplicate evidence signals")
    return {"evidence": clean}



def external_enabled() -> bool:
    return (os.getenv("AI_DISCLOSURE_APPROVED") == "true"
            and os.getenv("AI_TERMS_APPROVED") == "true"
            and os.getenv("AI_BILLING_MODE") == "free_only"
            and os.getenv("AI_WORKLOAD") == "inference"
            and bool(os.getenv("AI_LEDGER_HOST")))


def authorize_project(claims: dict, *, project_id: str | None, allowed_subjects: dict) -> None:
    """Only authoritative ownership and server-owned membership may authorize evidence.

    Caller must never derive project_id from untrusted alert labels or request text.
    """
    if (claims.get("role") not in {"sre", "platform-engineer"}
            or not project_id
            or project_id not in allowed_subjects.get(claims.get("sub"), [])):
        raise PermissionError("Project-scoped inference authorization required")


def validate_diagnosis(raw: str, evidence: list[dict]) -> Diagnosis:
    diagnosis = Diagnosis.model_validate_json(raw)
    if len(set(diagnosis.citations)) != len(diagnosis.citations):
        raise ValueError("Duplicate citations")
    if any(i < 0 or i >= len(evidence) for i in diagnosis.citations):
        raise ValueError("Invalid evidence citation")
    cited = [evidence[i] for i in diagnosis.citations]
    if diagnosis.assessment == "healthy" and any(e["state"] != "healthy" for e in evidence):
        raise ValueError("Unsupported healthy diagnosis")
    if diagnosis.assessment == "degraded" and not any(e["state"] == "degraded" for e in cited):
        raise ValueError("Unsupported degraded diagnosis")
    if all(e["state"] == "unknown" for e in evidence) and diagnosis.assessment != "insufficient_evidence":
        raise ValueError("Insufficient evidence")
    return diagnosis
