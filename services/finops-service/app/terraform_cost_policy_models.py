from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TerraformCostPolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class TerraformCostPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_monthly_increase_usd: float = Field(default=100.0, ge=0)
    max_monthly_increase_percent: float = Field(default=20.0, ge=0)
    block_if_evidence_incomplete: bool = True
    review_if_evidence_incomplete: bool = True


class TerraformCostComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_monthly_usd: float = Field(ge=0)
    proposed_monthly_usd: float = Field(ge=0)
    monthly_delta_usd: float
    monthly_delta_percent: float | None = None
    evidence_complete: bool
    resource_count: int = Field(ge=0)


class TerraformCostPolicyEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: TerraformCostPolicyDecision
    reasons: list[str] = Field(default_factory=list)
    comparison: TerraformCostComparison
    policy: TerraformCostPolicy
    generated_by: str = "cloudforge-finops-cost-policy-v1"
