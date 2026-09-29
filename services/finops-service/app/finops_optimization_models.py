from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OptimizationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class OptimizationDomain(str, Enum):
    KUBERNETES = "kubernetes"
    EKS = "eks"
    ECR = "ecr"
    S3 = "s3"
    RDS = "rds"
    NAT_GATEWAY = "nat_gateway"
    LOAD_BALANCER = "load_balancer"
    CLOUDWATCH = "cloudwatch"


class SavingsEvidence(BaseModel):
    monthly_usd: float = 0.0
    confidence: str = "unknown"
    calculation: str = "Savings not estimated: required pricing evidence is unavailable."
    pricing_source: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    evidence_available: bool = False


class OptimizationFinding(BaseModel):
    domain: OptimizationDomain
    resource_id: str
    severity: OptimizationSeverity

    metric: str

    observed_value: float | None = None
    recommended_value: float | None = None

    potential_monthly_savings_usd: float = 0.0
    savings: SavingsEvidence = Field(default_factory=SavingsEvidence)

    reason: str
    recommendation: str

    # No optimization finding can directly mutate infrastructure.
    action: str = "HUMAN_APPROVAL_REQUIRED"

    evidence: dict[str, Any] = Field(default_factory=dict)


class OptimizationReport(BaseModel):
    generated_by: str = "cloudforge-finops-v2b"

    findings: list[OptimizationFinding] = Field(default_factory=list)

    total_potential_monthly_savings_usd: float = 0.0

    finding_count: int = 0


class KubernetesWorkload(BaseModel):
    namespace: str
    workload: str

    replicas: float = 0.0

    cpu_request_cores: float = 0.0
    cpu_usage_cores: float = 0.0

    memory_request_bytes: float = 0.0
    memory_usage_bytes: float = 0.0

    cpu_limit_cores: float | None = None
    memory_limit_bytes: float | None = None

    # Optional pricing evidence. Prometheus does not invent these values.
    monthly_cpu_cost_usd_per_core: float | None = None
    monthly_memory_cost_usd_per_gib: float | None = None
    pricing_source: str | None = None


class HPAObservation(BaseModel):
    namespace: str
    hpa: str

    min_replicas: int
    max_replicas: int
    current_replicas: int
    desired_replicas: int


class NodeObservation(BaseModel):
    node: str

    cpu_allocatable_cores: float
    cpu_requested_cores: float
    cpu_usage_cores: float

    memory_allocatable_bytes: float
    memory_requested_bytes: float
    memory_usage_bytes: float

    # True means the collector actually observed the utilization metric.
    # Directly constructed observations remain backward-compatible.
    cpu_usage_available: bool = True
    memory_usage_available: bool = True

    monthly_cost_usd: float | None = None
    pricing_source: str | None = None



class KubernetesOptimizationSnapshot(BaseModel):
    workloads: list[KubernetesWorkload] = Field(
        default_factory=list
    )

    hpas: list[HPAObservation] = Field(
        default_factory=list
    )

    nodes: list[NodeObservation] = Field(
        default_factory=list
    )


class ECRObservation(BaseModel):
    repository: str
    image_count: int = 0
    storage_bytes: float = 0.0
    old_image_count: int | None = None
    old_image_storage_bytes: float | None = None
    monthly_storage_cost_usd: float | None = None
    pricing_source: str | None = None


class S3Observation(BaseModel):
    bucket: str
    storage_bytes: float = 0.0
    object_count: int = 0
    old_object_count: int | None = None
    old_object_storage_bytes: float | None = None
    monthly_storage_cost_usd: float | None = None
    pricing_source: str | None = None


class RDSObservation(BaseModel):
    resource_id: str
    cpu_percent: float | None = None
    connections: float | None = None
    free_storage_bytes: float | None = None
    monthly_cost_usd: float | None = None
    pricing_source: str | None = None


class AWSOptimizationObservation(BaseModel):
    ecr: list[ECRObservation] = Field(default_factory=list)
    s3: list[S3Observation] = Field(default_factory=list)
    rds: list[RDSObservation] = Field(default_factory=list)

    nat_gateways: list[str] = Field(default_factory=list)
    load_balancers: list[str] = Field(default_factory=list)
    cloudwatch_log_groups: list[str] = Field(default_factory=list)
