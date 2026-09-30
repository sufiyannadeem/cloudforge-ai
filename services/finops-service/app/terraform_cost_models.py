from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TerraformChangeAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "no-op"


class TerraformResourceType(str, Enum):
    AWS_INSTANCE = "aws_instance"
    AWS_EBS_VOLUME = "aws_ebs_volume"
    AWS_NAT_GATEWAY = "aws_nat_gateway"
    AWS_DB_INSTANCE = "aws_db_instance"
    AWS_LB = "aws_lb"
    AWS_S3_BUCKET = "aws_s3_bucket"
    AWS_EKS_NODE_GROUP = "aws_eks_node_group"


class TerraformPricingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_monthly_usd: float = Field(ge=0)
    source: str = Field(min_length=1)
    evidence_available: bool = False
    confidence: str = "unknown"
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("pricing source cannot be empty")
        return value


class TerraformResourceChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: TerraformResourceType
    resource_id: str = Field(min_length=1)
    action: TerraformChangeAction
    region: str = Field(min_length=1)

    current_quantity: float = Field(default=0, ge=0)
    proposed_quantity: float = Field(default=0, ge=0)

    pricing: TerraformPricingEvidence | None = None

    @field_validator("resource_id", "region")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value


class TerraformCostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: TerraformResourceType
    resource_id: str
    action: TerraformChangeAction
    region: str

    current_monthly_usd: float = 0.0
    proposed_monthly_usd: float = 0.0
    monthly_delta_usd: float = 0.0

    pricing_source: str | None = None
    confidence: str = "unknown"
    evidence_available: bool = False

    calculation: str
    assumptions: list[str] = Field(default_factory=list)


class TerraformCostEstimateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimates: list[TerraformCostEstimate] = Field(default_factory=list)
    total_current_monthly_usd: float = 0.0
    total_proposed_monthly_usd: float = 0.0
    total_monthly_delta_usd: float = 0.0
    evidence_complete: bool = False
    resource_count: int = 0
    generated_by: str = "cloudforge-finops-terraform-cost-v1"
