from __future__ import annotations

from .finops_optimization_models import (
    AWSOptimizationObservation,
    HPAObservation,
    KubernetesOptimizationSnapshot,
    KubernetesWorkload,
    OptimizationDomain,
    OptimizationFinding,
    OptimizationReport,
    OptimizationSeverity,
    SavingsEvidence,
)


class FinOpsOptimizationEngine:
    """
    Deterministic, read-only infrastructure optimization engine.

    Savings are calculated only when explicit pricing evidence is supplied.
    The engine never mutates Kubernetes, AWS, Terraform, or workloads.
    """

    CPU_OVER_REQUEST_RATIO = 3.0
    MEMORY_OVER_REQUEST_RATIO = 3.0
    CPU_UNDER_REQUEST_RATIO = 0.80
    MEMORY_UNDER_REQUEST_RATIO = 0.80
    LOW_NODE_UTILIZATION = 0.30
    HIGH_NODE_UTILIZATION = 0.85
    RECOMMENDED_USAGE_HEADROOM = 1.25

    def analyze_kubernetes(
        self,
        snapshot: KubernetesOptimizationSnapshot,
    ) -> list[OptimizationFinding]:
        findings: list[OptimizationFinding] = []

        for workload in snapshot.workloads:
            findings.extend(self._analyze_workload(workload))

        for hpa in snapshot.hpas:
            findings.extend(self._analyze_hpa(hpa))

        for node in snapshot.nodes:
            findings.extend(self._analyze_node(node))

        return findings

    def analyze_aws(
        self,
        observation: AWSOptimizationObservation,
    ) -> list[OptimizationFinding]:
        findings: list[OptimizationFinding] = []

        # ---------------------------------------------------------
        # ECR
        # ---------------------------------------------------------
        for ecr in observation.ecr:
            if ecr.image_count > 50:
                savings = self._ecr_savings(ecr)

                findings.append(
                    OptimizationFinding(
                        domain=OptimizationDomain.ECR,
                        resource_id=ecr.repository,
                        severity=OptimizationSeverity.WARNING,
                        metric="image_count",
                        observed_value=float(ecr.image_count),
                        recommended_value=50.0,
                        potential_monthly_savings_usd=savings.monthly_usd,
                        savings=savings,
                        reason="ECR repository contains a large number of images.",
                        recommendation=(
                            "Review image retention and configure an ECR lifecycle "
                            "policy for obsolete images."
                        ),
                        evidence={
                            "image_count": ecr.image_count,
                            "storage_bytes": ecr.storage_bytes,
                            "old_image_count": ecr.old_image_count,
                            "old_image_storage_bytes": ecr.old_image_storage_bytes,
                            "monthly_storage_cost_usd": ecr.monthly_storage_cost_usd,
                        },
                    )
                )

        # ---------------------------------------------------------
        # S3
        # ---------------------------------------------------------
        for bucket in observation.s3:
            if bucket.object_count > 100000:
                savings = self._s3_savings(bucket)

                findings.append(
                    OptimizationFinding(
                        domain=OptimizationDomain.S3,
                        resource_id=bucket.bucket,
                        severity=OptimizationSeverity.WARNING,
                        metric="object_count",
                        observed_value=float(bucket.object_count),
                        recommended_value=100000.0,
                        potential_monthly_savings_usd=savings.monthly_usd,
                        savings=savings,
                        reason=(
                            "S3 bucket contains a large object population that should "
                            "be evaluated for lifecycle/storage-class policy."
                        ),
                        recommendation=(
                            "Review object age and configure appropriate lifecycle "
                            "transitions where supported by workload requirements."
                        ),
                        evidence={
                            "object_count": bucket.object_count,
                            "storage_bytes": bucket.storage_bytes,
                            "old_object_count": bucket.old_object_count,
                            "old_object_storage_bytes": bucket.old_object_storage_bytes,
                            "monthly_storage_cost_usd": bucket.monthly_storage_cost_usd,
                        },
                    )
                )

        # ---------------------------------------------------------
        # RDS
        # ---------------------------------------------------------
        for rds in observation.rds:
            if rds.cpu_percent is not None and rds.cpu_percent < 20.0:
                savings = self._rds_savings(rds)

                findings.append(
                    OptimizationFinding(
                        domain=OptimizationDomain.RDS,
                        resource_id=rds.resource_id,
                        severity=OptimizationSeverity.WARNING,
                        metric="cpu_percent",
                        observed_value=rds.cpu_percent,
                        recommended_value=30.0,
                        potential_monthly_savings_usd=savings.monthly_usd,
                        savings=savings,
                        reason=(
                            "RDS CPU utilization is consistently low according to the "
                            "supplied observation."
                        ),
                        recommendation=(
                            "Review the instance class and workload requirements before "
                            "considering rightsizing."
                        ),
                        evidence={
                            "cpu_percent": rds.cpu_percent,
                            "connections": rds.connections,
                            "monthly_cost_usd": rds.monthly_cost_usd,
                        },
                    )
                )

        # ---------------------------------------------------------
        # NAT Gateway
        # ---------------------------------------------------------
        for nat in observation.nat_gateways:
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.NAT_GATEWAY,
                    resource_id=nat,
                    severity=OptimizationSeverity.INFO,
                    metric="nat_gateway_presence",
                    observed_value=1.0,
                    reason="NAT Gateway is a cost-bearing networking component.",
                    recommendation=(
                        "Review NAT data processing and architecture periodically. "
                        "Consider private connectivity alternatives where appropriate."
                    ),
                    evidence={"resource_id": nat},
                )
            )

        # ---------------------------------------------------------
        # Load Balancers
        # ---------------------------------------------------------
        for lb in observation.load_balancers:
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.LOAD_BALANCER,
                    resource_id=lb,
                    severity=OptimizationSeverity.INFO,
                    metric="load_balancer_presence",
                    observed_value=1.0,
                    reason=(
                        "Load Balancer incurs infrastructure and data-processing costs."
                    ),
                    recommendation=(
                        "Review utilization, target health, listener configuration, "
                        "and unnecessary load balancers."
                    ),
                    evidence={"resource_id": lb},
                )
            )

        # ---------------------------------------------------------
        # CloudWatch
        # ---------------------------------------------------------
        for log_group in observation.cloudwatch_log_groups:
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.CLOUDWATCH,
                    resource_id=log_group,
                    severity=OptimizationSeverity.INFO,
                    metric="log_group_presence",
                    observed_value=1.0,
                    reason=(
                        "CloudWatch log groups can accumulate storage and ingestion costs."
                    ),
                    recommendation=(
                        "Review retention periods and high-volume log sources."
                    ),
                    evidence={"log_group": log_group},
                )
            )

        return findings

    def build_report(
        self,
        *,
        kubernetes: KubernetesOptimizationSnapshot | None = None,
        aws: AWSOptimizationObservation | None = None,
    ) -> OptimizationReport:
        findings: list[OptimizationFinding] = []

        if kubernetes is not None:
            findings.extend(self.analyze_kubernetes(kubernetes))

        if aws is not None:
            findings.extend(self.analyze_aws(aws))

        savings = sum(
            finding.potential_monthly_savings_usd
            for finding in findings
        )

        return OptimizationReport(
            findings=findings,
            total_potential_monthly_savings_usd=round(savings, 2),
            finding_count=len(findings),
        )

    # =============================================================
    # Kubernetes analysis
    # =============================================================

    def _analyze_workload(
        self,
        workload: KubernetesWorkload,
    ) -> list[OptimizationFinding]:
        findings: list[OptimizationFinding] = []
        resource_id = f"{workload.namespace}/{workload.workload}"

        # ---------------------------------------------------------
        # CPU over-requesting
        # ---------------------------------------------------------
        if (
            workload.cpu_request_cores > 0
            and workload.cpu_usage_cores >= 0
            and workload.cpu_request_cores
            / max(workload.cpu_usage_cores, 0.001)
            >= self.CPU_OVER_REQUEST_RATIO
        ):
            savings = self._cpu_savings(workload)

            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.KUBERNETES,
                    resource_id=resource_id,
                    severity=OptimizationSeverity.WARNING,
                    metric="cpu_request_vs_usage",
                    observed_value=(
                        workload.cpu_request_cores
                        / max(workload.cpu_usage_cores, 0.001)
                    ),
                    potential_monthly_savings_usd=savings.monthly_usd,
                    savings=savings,
                    reason=(
                        "CPU request is substantially higher than observed CPU usage."
                    ),
                    recommendation=(
                        "Review CPU requests using representative peak/p95 workload "
                        "data before reducing them."
                    ),
                    evidence={
                        "cpu_request_cores": workload.cpu_request_cores,
                        "cpu_usage_cores": workload.cpu_usage_cores,
                        "replicas": workload.replicas,
                    },
                )
            )

        # ---------------------------------------------------------
        # CPU request headroom
        # ---------------------------------------------------------
        if (
            workload.cpu_request_cores > 0
            and workload.cpu_usage_cores
            > workload.cpu_request_cores * self.CPU_UNDER_REQUEST_RATIO
        ):
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.KUBERNETES,
                    resource_id=resource_id,
                    severity=OptimizationSeverity.WARNING,
                    metric="cpu_request_headroom",
                    observed_value=(
                        workload.cpu_usage_cores
                        / workload.cpu_request_cores
                    ),
                    reason=(
                        "Observed CPU usage is close to the configured CPU request."
                    ),
                    recommendation=(
                        "Review CPU request and workload peaks to avoid CPU throttling "
                        "during demand spikes."
                    ),
                    evidence={
                        "cpu_request_cores": workload.cpu_request_cores,
                        "cpu_usage_cores": workload.cpu_usage_cores,
                    },
                )
            )

        # ---------------------------------------------------------
        # Memory over-requesting
        # ---------------------------------------------------------
        if (
            workload.memory_request_bytes > 0
            and workload.memory_request_bytes
            / max(workload.memory_usage_bytes, 1)
            >= self.MEMORY_OVER_REQUEST_RATIO
        ):
            savings = self._memory_savings(workload)

            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.KUBERNETES,
                    resource_id=resource_id,
                    severity=OptimizationSeverity.WARNING,
                    metric="memory_request_vs_usage",
                    observed_value=(
                        workload.memory_request_bytes
                        / max(workload.memory_usage_bytes, 1)
                    ),
                    potential_monthly_savings_usd=savings.monthly_usd,
                    savings=savings,
                    reason=(
                        "Memory request is substantially higher than observed "
                        "memory usage."
                    ),
                    recommendation=(
                        "Review memory requests against representative peak usage "
                        "and OOM history before reducing them."
                    ),
                    evidence={
                        "memory_request_bytes": workload.memory_request_bytes,
                        "memory_usage_bytes": workload.memory_usage_bytes,
                    },
                )
            )

        # ---------------------------------------------------------
        # Possible idle workload
        # ---------------------------------------------------------
        if (
            workload.replicas > 1
            and workload.cpu_usage_cores == 0
            and workload.memory_usage_bytes == 0
        ):
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.KUBERNETES,
                    resource_id=resource_id,
                    severity=OptimizationSeverity.WARNING,
                    metric="workload_utilization",
                    observed_value=0.0,
                    recommended_value=1.0,
                    reason=(
                        "The workload has replicas but no measured CPU or memory usage."
                    ),
                    recommendation=(
                        "Verify telemetry first. If zero utilization is confirmed, "
                        "review whether replicas are required."
                    ),
                    evidence={
                        "replicas": workload.replicas,
                        "cpu_usage_cores": workload.cpu_usage_cores,
                        "memory_usage_bytes": workload.memory_usage_bytes,
                    },
                )
            )

        return findings

    def _analyze_hpa(
        self,
        hpa: HPAObservation,
    ) -> list[OptimizationFinding]:
        findings: list[OptimizationFinding] = []
        resource_id = f"{hpa.namespace}/{hpa.hpa}"

        if hpa.min_replicas == hpa.max_replicas:
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.KUBERNETES,
                    resource_id=resource_id,
                    severity=OptimizationSeverity.INFO,
                    metric="hpa_range",
                    observed_value=float(hpa.max_replicas),
                    recommendation=(
                        "Review whether a fixed HPA replica range is intentional; "
                        "min=max prevents scaling."
                    ),
                    reason="HPA minimum and maximum replicas are identical.",
                    evidence={
                        "min_replicas": hpa.min_replicas,
                        "max_replicas": hpa.max_replicas,
                        "current_replicas": hpa.current_replicas,
                        "desired_replicas": hpa.desired_replicas,
                    },
                )
            )

        if (
            hpa.current_replicas == hpa.max_replicas
            and hpa.desired_replicas == hpa.max_replicas
        ):
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.KUBERNETES,
                    resource_id=resource_id,
                    severity=OptimizationSeverity.WARNING,
                    metric="hpa_at_max_replicas",
                    observed_value=float(hpa.current_replicas),
                    reason="HPA is currently at its configured maximum.",
                    recommendation=(
                        "Review workload demand, resource requests, and maxReplicas "
                        "before increasing capacity."
                    ),
                    evidence={
                        "current_replicas": hpa.current_replicas,
                        "desired_replicas": hpa.desired_replicas,
                        "max_replicas": hpa.max_replicas,
                    },
                )
            )

        return findings

    def _analyze_node(self, node) -> list[OptimizationFinding]:
        findings: list[OptimizationFinding] = []

        cpu_utilization = None
        memory_utilization = None

        if (
            node.cpu_usage_available
            and node.cpu_allocatable_cores > 0
        ):
            cpu_utilization = (
                node.cpu_usage_cores
                / node.cpu_allocatable_cores
            )

        if (
            node.memory_usage_available
            and node.memory_allocatable_bytes > 0
        ):
            memory_utilization = (
                node.memory_usage_bytes
                / node.memory_allocatable_bytes
            )

        # Never interpret missing telemetry as zero utilization.
        available_utilizations = [
            value
            for value in (
                cpu_utilization,
                memory_utilization,
            )
            if value is not None
        ]

        if not available_utilizations:
            return findings

        # ---------------------------------------------------------
        # Low utilization
        # ---------------------------------------------------------
        if (
            cpu_utilization is not None
            and memory_utilization is not None
            and cpu_utilization < self.LOW_NODE_UTILIZATION
            and memory_utilization < self.LOW_NODE_UTILIZATION
        ):
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.EKS,
                    resource_id=node.node,
                    severity=OptimizationSeverity.WARNING,
                    metric="node_utilization",
                    observed_value=max(
                        cpu_utilization,
                        memory_utilization,
                    ),
                    recommended_value=0.50,
                    reason="Node CPU and memory utilization are both low.",
                    recommendation=(
                        "Review node count, workload placement, "
                        "and instance sizing before reducing capacity."
                    ),
                    evidence={
                        "cpu_utilization": cpu_utilization,
                        "memory_utilization": memory_utilization,
                        "cpu_utilization_available": node.cpu_usage_available,
                        "memory_utilization_available": node.memory_usage_available,
                        "cpu_requested_cores": node.cpu_requested_cores,
                        "memory_requested_bytes": node.memory_requested_bytes,
                    },
                )
            )

        # ---------------------------------------------------------
        # High utilization / capacity pressure
        # ---------------------------------------------------------
        if any(
            value > self.HIGH_NODE_UTILIZATION
            for value in available_utilizations
        ):
            findings.append(
                OptimizationFinding(
                    domain=OptimizationDomain.EKS,
                    resource_id=node.node,
                    severity=OptimizationSeverity.WARNING,
                    metric="node_capacity_pressure",
                    observed_value=max(available_utilizations),
                    reason=(
                        "Observed node utilization is high and may "
                        "constrain workload scheduling."
                    ),
                    recommendation=(
                        "Review workload requests, autoscaling, "
                        "and node-group capacity."
                    ),
                    evidence={
                        "cpu_utilization": cpu_utilization,
                        "memory_utilization": memory_utilization,
                        "cpu_utilization_available": node.cpu_usage_available,
                        "memory_utilization_available": node.memory_usage_available,
                    },
                )
            )

        return findings

    # =============================================================
    # Deterministic savings calculations
    # =============================================================

    def _cpu_savings(
        self,
        workload: KubernetesWorkload,
    ) -> SavingsEvidence:
        """
        Estimate monthly CPU savings only when an explicit monthly
        cost per requested CPU core is supplied.

        Target request = observed usage * 1.25 headroom.
        Savings = excess requested cores * explicit monthly price.
        """

        price = workload.monthly_cpu_cost_usd_per_core
        usage = max(workload.cpu_usage_cores, 0.0)
        request = max(workload.cpu_request_cores, 0.0)

        if price is None or price <= 0:
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation=(
                    "Savings not estimated: required CPU pricing evidence "
                    "is unavailable."
                ),
                pricing_source=workload.pricing_source,
                assumptions=[
                    "No CPU price was assumed.",
                    "No external cloud pricing was inferred.",
                ],
                evidence_available=False,
            )

        if request <= 0 or usage < 0:
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation="Savings not estimated: invalid CPU utilization evidence.",
                pricing_source=workload.pricing_source,
                assumptions=[],
                evidence_available=False,
            )

        recommended_request = usage * self.RECOMMENDED_USAGE_HEADROOM
        reducible_cores = max(request - recommended_request, 0.0)
        monthly_savings = reducible_cores * price

        return SavingsEvidence(
            monthly_usd=round(monthly_savings, 2),
            confidence="high",
            calculation=(
                f"({request:.6f} requested cores - "
                f"{recommended_request:.6f} recommended cores) × "
                f"${price:.6f}/core/month"
            ),
            pricing_source=workload.pricing_source,
            assumptions=[
                "Recommended CPU request uses 1.25x observed usage.",
                "The supplied CPU monthly price is authoritative for this estimate.",
                "The estimate does not account for workload peaks outside the observed window.",
            ],
            evidence_available=True,
        )

    def _memory_savings(
        self,
        workload: KubernetesWorkload,
    ) -> SavingsEvidence:
        """
        Estimate monthly memory savings only when an explicit monthly
        cost per GiB is supplied.
        """

        price = workload.monthly_memory_cost_usd_per_gib
        usage = max(workload.memory_usage_bytes, 0)
        request = max(workload.memory_request_bytes, 0)

        if price is None or price <= 0:
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation=(
                    "Savings not estimated: required memory pricing evidence "
                    "is unavailable."
                ),
                pricing_source=workload.pricing_source,
                assumptions=[
                    "No memory price was assumed.",
                    "No external cloud pricing was inferred.",
                ],
                evidence_available=False,
            )

        if request <= 0:
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation="Savings not estimated: invalid memory request evidence.",
                pricing_source=workload.pricing_source,
                assumptions=[],
                evidence_available=False,
            )

        gib = 1024 ** 3
        usage_gib = usage / gib
        request_gib = request / gib
        recommended_request_gib = usage_gib * self.RECOMMENDED_USAGE_HEADROOM

        reducible_gib = max(
            request_gib - recommended_request_gib,
            0.0,
        )

        monthly_savings = reducible_gib * price

        return SavingsEvidence(
            monthly_usd=round(monthly_savings, 2),
            confidence="high",
            calculation=(
                f"({request_gib:.6f} requested GiB - "
                f"{recommended_request_gib:.6f} recommended GiB) × "
                f"${price:.6f}/GiB/month"
            ),
            pricing_source=workload.pricing_source,
            assumptions=[
                "Recommended memory request uses 1.25x observed usage.",
                "The supplied memory monthly price is authoritative for this estimate.",
                "The estimate does not account for workload peaks outside the observed window.",
            ],
            evidence_available=True,
        )

    def _ecr_savings(
        self,
        ecr,
    ) -> SavingsEvidence:
        """
        Estimate ECR savings only from explicitly identified old-image
        storage and an explicit monthly storage price.

        Total repository storage is never treated as obsolete storage.
        """

        old_storage = ecr.old_image_storage_bytes
        monthly_storage_cost = ecr.monthly_storage_cost_usd

        if (
            old_storage is None
            or old_storage <= 0
            or monthly_storage_cost is None
            or monthly_storage_cost <= 0
        ):
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation=(
                    "Savings not estimated: explicit old-image storage and "
                    "monthly pricing evidence are required."
                ),
                pricing_source=ecr.pricing_source,
                assumptions=[
                    "Only explicitly identified old-image storage is eligible.",
                    "Total repository storage is not assumed to be obsolete.",
                    "No external ECR pricing was inferred.",
                ],
                evidence_available=False,
            )

        total_storage = max(ecr.storage_bytes, 0)

        if total_storage <= 0:
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation=(
                    "Savings not estimated: repository storage evidence is invalid."
                ),
                pricing_source=ecr.pricing_source,
                assumptions=[],
                evidence_available=False,
            )

        old_fraction = min(old_storage / total_storage, 1.0)
        monthly_savings = monthly_storage_cost * old_fraction

        return SavingsEvidence(
            monthly_usd=round(monthly_savings, 2),
            confidence="high",
            calculation=(
                f"${monthly_storage_cost:.6f}/month × "
                f"({old_storage} old-image bytes / {total_storage} total bytes)"
            ),
            pricing_source=ecr.pricing_source,
            assumptions=[
                "Only identified old-image storage is considered removable.",
                "The supplied monthly storage cost represents the repository storage population.",
                "Deleting obsolete images is subject to retention and rollback requirements.",
            ],
            evidence_available=True,
        )

    def _s3_savings(
        self,
        bucket,
    ) -> SavingsEvidence:
        """
        Estimate S3 savings only from explicitly identified old-object
        storage and an explicit monthly storage price.

        Total bucket storage is never assumed to be obsolete.
        """

        old_storage = bucket.old_object_storage_bytes
        monthly_storage_cost = bucket.monthly_storage_cost_usd

        if (
            old_storage is None
            or old_storage <= 0
            or monthly_storage_cost is None
            or monthly_storage_cost <= 0
        ):
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation=(
                    "Savings not estimated: explicit old-object storage and "
                    "monthly pricing evidence are required."
                ),
                pricing_source=bucket.pricing_source,
                assumptions=[
                    "Only explicitly identified old-object storage is eligible.",
                    "Total bucket storage is not assumed to be obsolete.",
                    "No external S3 pricing was inferred.",
                ],
                evidence_available=False,
            )

        total_storage = max(bucket.storage_bytes, 0)

        if total_storage <= 0:
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation=(
                    "Savings not estimated: bucket storage evidence is invalid."
                ),
                pricing_source=bucket.pricing_source,
                assumptions=[],
                evidence_available=False,
            )

        old_fraction = min(old_storage / total_storage, 1.0)
        monthly_savings = monthly_storage_cost * old_fraction

        return SavingsEvidence(
            monthly_usd=round(monthly_savings, 2),
            confidence="high",
            calculation=(
                f"${monthly_storage_cost:.6f}/month × "
                f"({old_storage} old-object bytes / {total_storage} total bytes)"
            ),
            pricing_source=bucket.pricing_source,
            assumptions=[
                "Only identified old-object storage is considered removable or transitionable.",
                "The supplied monthly storage cost represents the bucket storage population.",
                "Lifecycle transitions must preserve application and retention requirements.",
            ],
            evidence_available=True,
        )

    def _rds_savings(
        self,
        rds,
    ) -> SavingsEvidence:
        """
        RDS savings require an explicit monthly instance-cost observation.
        No AWS instance pricing is inferred by the engine.
        """

        monthly_cost = rds.monthly_cost_usd

        if monthly_cost is None or monthly_cost <= 0:
            return SavingsEvidence(
                monthly_usd=0.0,
                confidence="unknown",
                calculation=(
                    "Savings not estimated: explicit RDS monthly cost evidence "
                    "is unavailable."
                ),
                pricing_source=rds.pricing_source,
                assumptions=[
                    "No RDS instance price was assumed.",
                    "Low CPU utilization alone does not establish a savings amount.",
                ],
                evidence_available=False,
            )

        # This finding is a rightsizing review, not an automatic downsizing
        # recommendation. Use a conservative, auditable 0% savings estimate
        # unless an explicit target class/cost difference is supplied.
        return SavingsEvidence(
            monthly_usd=0.0,
            confidence="unknown",
            calculation=(
                "Savings not estimated: an explicit target RDS class and "
                "target monthly cost are required to calculate rightsizing savings."
            ),
            pricing_source=rds.pricing_source,
            assumptions=[
                f"Current monthly RDS cost observed: ${monthly_cost:.2f}.",
                "Low CPU utilization alone does not prove a lower-cost target class is suitable.",
                "No target RDS pricing was inferred.",
            ],
            evidence_available=False,
        )
