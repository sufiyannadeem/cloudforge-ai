from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TerraformPlanArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    workspace: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    region: str = Field(min_length=1)

    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    resource_count: int = Field(ge=0)

    plan_hash: str = Field(
        min_length=64,
        max_length=64,
    )

    @field_validator(
        "artifact_id",
        "source",
        "workspace",
        "environment",
        "region",
        "plan_hash",
    )
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value cannot be empty")

        return value


class TerraformPlanEvidenceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parsed_resource_count: int = Field(ge=0)

    priced_resource_count: int = Field(ge=0)

    missing_pricing_resource_count: int = Field(ge=0)

    coverage_percent: float = Field(
        ge=0,
        le=100,
    )

    complete: bool


class TerraformPlanArtifactCostResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact: TerraformPlanArtifact

    cost_report: object

    parse_issues: list[str] = Field(
        default_factory=list
    )

    unsupported_resources: list[str] = Field(
        default_factory=list
    )

    parsed_resource_count: int = Field(ge=0)

    evidence_coverage: TerraformPlanEvidenceCoverage

    generated_by: str = (
        "cloudforge-finops-terraform-cost-evidence-v1"
    )
