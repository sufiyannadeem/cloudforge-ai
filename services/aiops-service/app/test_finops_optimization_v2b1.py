from __future__ import annotations

from .finops_optimization_engine import FinOpsOptimizationEngine
from .finops_optimization_models import (
    AWSOptimizationObservation,
    ECRObservation,
    KubernetesOptimizationSnapshot,
    KubernetesWorkload,
    OptimizationDomain,
    RDSObservation,
    S3Observation,
)
from .finops_optimization_prometheus import PrometheusFinOpsCollector


def test_cpu_savings_requires_pricing_evidence():
    finding = next(
        f
        for f in FinOpsOptimizationEngine()
        .build_report(
            kubernetes=KubernetesOptimizationSnapshot(
                workloads=[
                    KubernetesWorkload(
                        namespace="prod",
                        workload="api",
                        replicas=2,
                        cpu_request_cores=2.0,
                        cpu_usage_cores=0.25,
                    )
                ]
            )
        )
        .findings
        if f.metric == "cpu_request_vs_usage"
    )

    assert finding.potential_monthly_savings_usd == 0.0
    assert finding.savings.confidence == "unknown"
    assert finding.savings.evidence_available is False


def test_cpu_savings_is_deterministic_with_pricing():
    report = FinOpsOptimizationEngine().build_report(
        kubernetes=KubernetesOptimizationSnapshot(
            workloads=[
                KubernetesWorkload(
                    namespace="prod",
                    workload="api",
                    replicas=2,
                    cpu_request_cores=2.0,
                    cpu_usage_cores=0.25,
                    monthly_cpu_cost_usd_per_core=10.0,
                    pricing_source="test-rate-card",
                )
            ]
        )
    )

    finding = next(
        f for f in report.findings if f.metric == "cpu_request_vs_usage"
    )

    assert finding.potential_monthly_savings_usd == 16.88
    assert finding.savings.pricing_source == "test-rate-card"
    assert "2.0" in finding.savings.calculation
    assert report.total_potential_monthly_savings_usd == 16.88


def test_aws_savings_requires_explicit_old_storage_and_price():
    report = FinOpsOptimizationEngine().build_report(
        aws=AWSOptimizationObservation(
            ecr=[
                ECRObservation(
                    repository="repo",
                    image_count=100,
                    storage_bytes=1000,
                )
            ],
            s3=[
                S3Observation(
                    bucket="bucket",
                    object_count=200000,
                    storage_bytes=1000,
                )
            ],
            rds=[
                RDSObservation(
                    resource_id="db",
                    cpu_percent=5.0,
                    monthly_cost_usd=100.0,
                )
            ],
        )
    )

    assert report.total_potential_monthly_savings_usd == 0.0
    assert all(
        f.savings.evidence_available is False
        for f in report.findings
    )


def test_ecr_savings_uses_identified_old_storage_only():
    report = FinOpsOptimizationEngine().build_report(
        aws=AWSOptimizationObservation(
            ecr=[
                ECRObservation(
                    repository="repo",
                    image_count=100,
                    storage_bytes=100 * 1024**3,
                    old_image_count=40,
                    old_image_storage_bytes=20 * 1024**3,
                    monthly_storage_cost_usd=50.0,
                    pricing_source="verified-rate-card",
                )
            ]
        )
    )

    finding = next(
        f for f in report.findings
        if f.domain == OptimizationDomain.ECR
    )

    assert finding.potential_monthly_savings_usd == 10.0
    assert finding.savings.evidence_available is True


def test_s3_savings_uses_identified_old_storage_only():
    report = FinOpsOptimizationEngine().build_report(
        aws=AWSOptimizationObservation(
            s3=[
                S3Observation(
                    bucket="bucket",
                    object_count=200000,
                    storage_bytes=200 * 1024**3,
                    old_object_count=50000,
                    old_object_storage_bytes=50 * 1024**3,
                    monthly_storage_cost_usd=40.0,
                    pricing_source="verified-rate-card",
                )
            ]
        )
    )

    finding = next(
        f for f in report.findings
        if f.domain == OptimizationDomain.S3
    )

    assert finding.potential_monthly_savings_usd == 10.0


class _FakeResult:
    def __init__(self, value):
        self.value = value


class _FakePrometheus:
    def query(self, expression: str):
        # Pod -> workload owner mapping.
        if "kube_pod_owner" in expression:
            return _FakeResult(
                [
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-1",
                            "owner_kind": "Deployment",
                            "owner_name": "api",
                        },
                        "value": ["0", "1"],
                    },
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-2",
                            "owner_kind": "Deployment",
                            "owner_name": "api",
                        },
                        "value": ["0", "1"],
                    },
                ]
            )

        # Deployment-owned pods do not require ReplicaSet resolution.
        if "kube_replicaset_owner" in expression:
            return _FakeResult([])

        # CPU requests.
        if (
            'resource="cpu"' in expression
            and "requests" in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-1",
                        },
                        "value": ["0", "0.5"],
                    },
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-2",
                        },
                        "value": ["0", "0.5"],
                    },
                ]
            )

        # Memory requests.
        if (
            'resource="memory"' in expression
            and "requests" in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-1",
                        },
                        "value": ["0", str(512 * 1024**2)],
                    },
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-2",
                        },
                        "value": ["0", str(512 * 1024**2)],
                    },
                ]
            )

        # CPU limits.
        if (
            'resource="cpu"' in expression
            and "limits" in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-1",
                        },
                        "value": ["0", "1"],
                    },
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-2",
                        },
                        "value": ["0", "1"],
                    },
                ]
            )

        # Memory limits unavailable.
        if (
            'resource="memory"' in expression
            and "limits" in expression
        ):
            return _FakeResult([])

        # IMPORTANT:
        # Node-level CPU usage must be checked BEFORE the generic
        # container CPU usage matcher. Otherwise the generic matcher
        # shadows the node query.
        if (
            "container_cpu_usage_seconds_total" in expression
            and "sum by (node)" in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "node": "node-a",
                        },
                        "value": ["0", "1"],
                    }
                ]
            )

        # Workload/pod CPU usage.
        if "container_cpu_usage_seconds_total" in expression:
            return _FakeResult(
                [
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-1",
                        },
                        "value": ["0", "0.1"],
                    },
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-2",
                        },
                        "value": ["0", "0.2"],
                    },
                ]
            )

        # Workload/pod memory usage.
        if (
            "container_memory_working_set_bytes" in expression
            and "sum by (namespace, pod)" in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-1",
                        },
                        "value": ["0", str(200 * 1024**2)],
                    },
                    {
                        "metric": {
                            "namespace": "prod",
                            "pod": "api-2",
                        },
                        "value": ["0", str(300 * 1024**2)],
                    },
                ]
            )

        # HPA data unavailable in this fixture.
        if "kube_horizontalpodautoscaler" in expression:
            return _FakeResult([])

        # Node allocatable CPU.
        if 'kube_node_status_allocatable{resource="cpu"' in expression:
            return _FakeResult(
                [
                    {
                        "metric": {
                            "node": "node-a",
                        },
                        "value": ["0", "4"],
                    }
                ]
            )

        # Node allocatable memory.
        if 'kube_node_status_allocatable{resource="memory"' in expression:
            return _FakeResult(
                [
                    {
                        "metric": {
                            "node": "node-a",
                        },
                        "value": ["0", str(8 * 1024**3)],
                    }
                ]
            )

        # Node requested CPU.
        if (
            'kube_pod_container_resource_requests{resource="cpu"'
            in expression
            and "sum by (node)" in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "node": "node-a",
                        },
                        "value": ["0", "1"],
                    }
                ]
            )

        # Node requested memory.
        if (
            'kube_pod_container_resource_requests{resource="memory"'
            in expression
            and "sum by (node)" in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "node": "node-a",
                        },
                        "value": ["0", str(1024**3)],
                    }
                ]
            )

        # Node memory usage.
        if (
            "sum by (node) (container_memory_working_set_bytes"
            in expression
        ):
            return _FakeResult(
                [
                    {
                        "metric": {
                            "node": "node-a",
                        },
                        "value": ["0", str(2 * 1024**3)],
                    }
                ]
            )

        return _FakeResult([])


def test_prometheus_aggregates_pods_to_workload_and_collects_node_memory():
    collector = PrometheusFinOpsCollector(
        client=_FakePrometheus()
    )

    snapshot = collector.collect_snapshot()

    assert len(snapshot.workloads) == 1

    workload = snapshot.workloads[0]

    assert workload.workload == "api"
    assert workload.replicas == 2
    assert workload.cpu_request_cores == 1.0
    assert workload.cpu_usage_cores == 0.30000000000000004
    assert workload.cpu_limit_cores == 2.0
    assert workload.memory_usage_bytes == 500 * 1024**2

    assert len(snapshot.nodes) == 1
    assert snapshot.nodes[0].memory_usage_bytes == 2 * 1024**3
    assert snapshot.nodes[0].cpu_usage_available is True
    assert snapshot.nodes[0].memory_usage_available is True


def test_prometheus_missing_node_utilization_is_not_treated_as_zero():
    class _MissingNodeUsagePrometheus(_FakePrometheus):
        def query(self, expression: str):
            if (
                "container_cpu_usage_seconds_total" in expression
                and "sum by (node)" in expression
            ):
                return _FakeResult([])

            if (
                "sum by (node) (container_memory_working_set_bytes"
                in expression
            ):
                return _FakeResult([])

            return super().query(expression)

    collector = PrometheusFinOpsCollector(
        client=_MissingNodeUsagePrometheus()
    )

    snapshot = collector.collect_snapshot()

    assert len(snapshot.nodes) == 1

    node = snapshot.nodes[0]

    assert node.cpu_usage_available is False
    assert node.memory_usage_available is False

    report = FinOpsOptimizationEngine().build_report(
        kubernetes=snapshot
    )

    assert not any(
        finding.resource_id == "node-a"
        and finding.metric
        in {
            "node_utilization",
            "node_capacity_pressure",
        }
        for finding in report.findings
    )


def test_prometheus_owner_mapping_deployment_remains_workload():
    class _DeploymentPrometheus(_FakePrometheus):
        def query(self, expression: str):
            if "kube_pod_owner" in expression:
                return _FakeResult(
                    [
                        {
                            "metric": {
                                "namespace": "prod",
                                "pod": "api-1",
                                "owner_kind": "ReplicaSet",
                                "owner_name": "api-7f8d9c",
                            },
                            "value": ["0", "1"],
                        },
                        {
                            "metric": {
                                "namespace": "prod",
                                "pod": "api-2",
                                "owner_kind": "ReplicaSet",
                                "owner_name": "api-7f8d9c",
                            },
                            "value": ["0", "1"],
                        },
                    ]
                )

            if "kube_replicaset_owner" in expression:
                return _FakeResult(
                    [
                        {
                            "metric": {
                                "namespace": "prod",
                                "replicaset": "api-7f8d9c",
                                "owner_kind": "Deployment",
                                "owner_name": "api",
                            },
                            "value": ["0", "1"],
                        }
                    ]
                )

            return super().query(expression)

    snapshot = PrometheusFinOpsCollector(
        client=_DeploymentPrometheus()
    ).collect_snapshot()

    assert len(snapshot.workloads) == 1
    assert snapshot.workloads[0].workload == "api"
    assert snapshot.workloads[0].replicas == 2
