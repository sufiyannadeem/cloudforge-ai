from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .terraform_cost_models import TerraformResourceType


class TerraformPricingRateCard(BaseModel):
    """
    Explicit pricing evidence for one Terraform resource type, region and
    pricing unit.

    This model never infers or retrieves pricing automatically.
    """

    model_config = ConfigDict(extra="forbid")

    resource_type: TerraformResourceType
    region: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    unit_monthly_usd: float = Field(ge=0)
    source: str = Field(min_length=1)
    evidence_available: bool = False
    confidence: str = "unknown"
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("region", "unit", "source")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value cannot be empty")

        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: str) -> str:
        value = value.strip().lower()

        allowed = {
            "unknown",
            "low",
            "medium",
            "high",
        }

        if value not in allowed:
            raise ValueError(
                "confidence must be one of: unknown, low, medium, high"
            )

        return value


class TerraformPricingRateCardResponse(TerraformPricingRateCard):
    pass


class TerraformPricingRateCardListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[TerraformPricingRateCardResponse] = Field(
        default_factory=list
    )
    count: int = 0
    generated_by: str = "cloudforge-finops-pricing-v1"
