from __future__ import annotations

from .finops_optimization_engine import (
    FinOpsOptimizationEngine,
)
from .finops_optimization_models import (
    AWSOptimizationObservation,
    ECRObservation,
    HPAObservation,
    KubernetesOptimizationSnapshot,
    KubernetesWorkload,
    NodeObservation,
    OptimizationDomain,
    OptimizationSeverity,
    RDSObservation,
    S3Observation,
)


def test_cpu_over_request():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        workloads=[
            KubernetesWorkload(
                namespace="production",
                workload="payment-service",
                replicas=3,
                cpu_request_cores=1.0,
                cpu_usage_cores=0.2,
                memory_request_bytes=512 * 1024 * 1024,
                memory_usage_bytes=256 * 1024 * 1024,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    finding = next(
        finding
        for finding in report.findings
        if finding.metric == "cpu_request_vs_usage"
    )

    assert finding.domain == OptimizationDomain.KUBERNETES
    assert finding.severity == OptimizationSeverity.WARNING


def test_memory_over_request():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        workloads=[
            KubernetesWorkload(
                namespace="production",
                workload="catalog-service",
                replicas=2,
                cpu_request_cores=0.2,
                cpu_usage_cores=0.1,
                memory_request_bytes=2 * 1024 * 1024 * 1024,
                memory_usage_bytes=256 * 1024 * 1024,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    assert any(
        finding.metric == "memory_request_vs_usage"
        for finding in report.findings
    )


def test_idle_workload():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        workloads=[
            KubernetesWorkload(
                namespace="production",
                workload="unused-service",
                replicas=2,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    assert any(
        finding.metric == "workload_utilization"
        for finding in report.findings
    )


def test_hpa_fixed_range():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        hpas=[
            HPAObservation(
                namespace="production",
                hpa="payment-hpa",
                min_replicas=3,
                max_replicas=3,
                current_replicas=3,
                desired_replicas=3,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    assert any(
        finding.metric == "hpa_range"
        for finding in report.findings
    )


def test_hpa_at_max():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        hpas=[
            HPAObservation(
                namespace="production",
                hpa="api-hpa",
                min_replicas=2,
                max_replicas=10,
                current_replicas=10,
                desired_replicas=10,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    assert any(
        finding.metric == "hpa_at_max_replicas"
        for finding in report.findings
    )


def test_underutilized_node():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        nodes=[
            NodeObservation(
                node="node-1",
                cpu_allocatable_cores=4,
                cpu_requested_cores=1,
                cpu_usage_cores=0.5,
                memory_allocatable_bytes=8 * 1024**3,
                memory_requested_bytes=2 * 1024**3,
                memory_usage_bytes=1 * 1024**3,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    assert any(
        finding.domain == OptimizationDomain.EKS
        for finding in report.findings
    )


def test_high_node_utilization():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        nodes=[
            NodeObservation(
                node="node-2",
                cpu_allocatable_cores=4,
                cpu_requested_cores=4,
                cpu_usage_cores=3.8,
                memory_allocatable_bytes=8 * 1024**3,
                memory_requested_bytes=7 * 1024**3,
                memory_usage_bytes=7 * 1024**3,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    assert any(
        finding.metric == "node_capacity_pressure"
        for finding in report.findings
    )


def test_ecr_optimization():

    engine = FinOpsOptimizationEngine()

    observation = AWSOptimizationObservation(
        ecr=[
            ECRObservation(
                repository="cloudforge/api",
                image_count=100,
                storage_bytes=10 * 1024**3,
            )
        ]
    )

    report = engine.build_report(
        aws=observation
    )

    assert any(
        finding.domain == OptimizationDomain.ECR
        for finding in report.findings
    )


def test_s3_optimization():

    engine = FinOpsOptimizationEngine()

    observation = AWSOptimizationObservation(
        s3=[
            S3Observation(
                bucket="cloudforge-artifacts",
                object_count=200000,
                storage_bytes=20 * 1024**3,
            )
        ]
    )

    report = engine.build_report(
        aws=observation
    )

    assert any(
        finding.domain == OptimizationDomain.S3
        for finding in report.findings
    )


def test_rds_low_cpu():

    engine = FinOpsOptimizationEngine()

    observation = AWSOptimizationObservation(
        rds=[
            RDSObservation(
                resource_id="cloudforge-db",
                cpu_percent=8.0,
                connections=4,
            )
        ]
    )

    report = engine.build_report(
        aws=observation
    )

    assert any(
        finding.domain == OptimizationDomain.RDS
        for finding in report.findings
    )


def test_network_and_cloudwatch():

    engine = FinOpsOptimizationEngine()

    observation = AWSOptimizationObservation(
        nat_gateways=["nat-123"],
        load_balancers=["alb-123"],
        cloudwatch_log_groups=[
            "/aws/cloudforge/application"
        ],
    )

    report = engine.build_report(
        aws=observation
    )

    domains = {
        finding.domain
        for finding in report.findings
    }

    assert OptimizationDomain.NAT_GATEWAY in domains
    assert OptimizationDomain.LOAD_BALANCER in domains
    assert OptimizationDomain.CLOUDWATCH in domains


def test_all_actions_require_human_approval():

    engine = FinOpsOptimizationEngine()

    snapshot = KubernetesOptimizationSnapshot(
        workloads=[
            KubernetesWorkload(
                namespace="production",
                workload="api",
                replicas=2,
                cpu_request_cores=1,
                cpu_usage_cores=0.1,
            )
        ]
    )

    report = engine.build_report(
        kubernetes=snapshot
    )

    assert report.findings

    assert all(
        finding.action == "HUMAN_APPROVAL_REQUIRED"
        for finding in report.findings
    )


def test_empty_report():

    engine = FinOpsOptimizationEngine()

    report = engine.build_report()

    assert report.finding_count == 0
    assert report.findings == []


if __name__ == "__main__":
    tests = [
        test_cpu_over_request,
        test_memory_over_request,
        test_idle_workload,
        test_hpa_fixed_range,
        test_hpa_at_max,
        test_underutilized_node,
        test_high_node_utilization,
        test_ecr_optimization,
        test_s3_optimization,
        test_rds_low_cpu,
        test_network_and_cloudwatch,
        test_all_actions_require_human_approval,
        test_empty_report,
    ]

    for test in tests:
        test()

    print(
        "ALL FINOPS OPTIMIZATION TESTS PASSED"
    )
