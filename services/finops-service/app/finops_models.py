from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CostSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ResourceType(str, Enum):
    EKS = "eks"
    EC2 = "ec2"
    RDS = "rds"
    ECR = "ecr"
    S3 = "s3"
    CLOUDWATCH = "cloudwatch"
    LOAD_BALANCER = "load_balancer"
    NAT_GATEWAY = "nat_gateway"
    UNKNOWN = "unknown"


class CostFinding(BaseModel):
    resource_id: str
    resource_type: ResourceType
    service: str

    estimated_monthly_cost: float = 0.0

    severity: CostSeverity = CostSeverity.INFO

    idle: bool = False
    untagged: bool = False

    region: str | None = None

    tags: dict[str, str] = Field(
        default_factory=dict
    )

    reason: str

    recommendation: str


class CostSummary(BaseModel):
    currency: str = "USD"

    total_estimated_monthly_cost: float = 0.0

    idle_monthly_cost: float = 0.0

    untagged_resource_count: int = 0

    findings_count: int = 0

    critical_findings: int = 0

    warning_findings: int = 0

    info_findings: int = 0


class FinOpsReport(BaseModel):
    account_id: str | None = None
    region: str

    summary: CostSummary

    findings: list[CostFinding] = Field(
        default_factory=list
    )

    generated_by: str = "cloudforge-finops"

    cost_data_source: str = "local-analysis"

class AWSServiceCost(BaseModel):
    service: str

    amount: float = 0.0

    currency: str = "USD"

    start_date: str
    end_date: str


class AWSResource(BaseModel):
    resource_arn: str

    resource_type: ResourceType

    service: str

    region: str

    tags: dict[str, str] = Field(
        default_factory=dict
    )

    tagged: bool = True


class AWSFinOpsSnapshot(BaseModel):
    account_id: str

    region: str

    cost_start_date: str

    cost_end_date: str

    service_costs: list[AWSServiceCost] = Field(
        default_factory=list
    )

    resources: list[AWSResource] = Field(
        default_factory=list
    )

    resource_inventory_scope: str = (
        "tagged-or-previously-tagged-resources"
    )

    cost_data_source: str = (
        "aws-cost-explorer"
    )

    resource_data_source: str = (
        "aws-resource-groups-tagging-api"
    )

class FinOpsAWSResponse(BaseModel):
    snapshot: AWSFinOpsSnapshot
    report: FinOpsReport
