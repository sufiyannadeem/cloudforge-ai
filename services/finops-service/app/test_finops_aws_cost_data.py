from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from botocore.exceptions import ClientError

from .aws_finops_client import AWSFinOpsClient, AWSFinOpsError
from .aws_finops_service import AWSFinOpsService
from .finops_cost_intelligence import (
    BudgetStatus,
    CostTrend,
    calculate_period_trend,
    detect_cost_anomalies,
)
from .finops_models import (
    AWSFinOpsSnapshot,
    AWSResource,
    AWSServiceCost,
    ResourceType,
)


def test_cost_history_calculation():
    client = MagicMock()
    client.get_daily_cost_history.return_value = [
        {"date": "2026-10-01", "amount": 10.50, "currency": "USD"},
        {"date": "2026-10-02", "amount": 12.25, "currency": "USD"},
        {"date": "2026-10-03", "amount": 9.25, "currency": "USD"},
    ]
    service = AWSFinOpsService(client=client)

    history = service.get_cost_history(start_date="2026-10-01", end_date="2026-10-04")

    assert history.total_cost == 32.00
    assert history.average_daily_cost == 10.67
    assert len(history.points) == 3
    assert history.currency == "USD"


def test_cost_history_empty_data():
    client = MagicMock()
    client.get_daily_cost_history.return_value = []
    service = AWSFinOpsService(client=client)

    history = service.get_cost_history(start_date="2026-10-01", end_date="2026-10-04")

    assert history.total_cost == 0.0
    assert history.average_daily_cost == 0.0
    assert history.points == []


def test_cost_trend_calculation_stable_and_division_by_zero():
    trend_zero = calculate_period_trend(
        current_cost=0.0,
        previous_cost=0.0,
        start_date="2026-10-01",
        end_date="2026-10-10",
        comparison_start_date="2026-09-21",
        comparison_end_date="2026-10-01",
    )
    assert trend_zero.change_amount == 0.0
    assert trend_zero.change_percent is None
    assert trend_zero.trend == CostTrend.STABLE

    trend_up = calculate_period_trend(
        current_cost=150.0,
        previous_cost=100.0,
        start_date="2026-10-01",
        end_date="2026-10-10",
        comparison_start_date="2026-09-21",
        comparison_end_date="2026-10-01",
    )
    assert trend_up.change_amount == 50.0
    assert trend_up.change_percent == 50.0
    assert trend_up.trend == CostTrend.WORSENING


def test_cost_anomalies_detection():
    # Stable points: mean=10, stddev=0
    stable_points = [
        {"date": f"2026-10-0{i}", "amount": 10.0, "currency": "USD"}
        for i in range(1, 8)
    ]
    anomalies = detect_cost_anomalies(
        points=stable_points,
        start_date="2026-10-01",
        end_date="2026-10-08",
        threshold=2.5,
    )
    assert anomalies.anomalies == []

    # One extreme outlier spike
    spike_points = stable_points + [
        {"date": "2026-10-08", "amount": 100.0, "currency": "USD"}
    ]
    anomalies_spiked = detect_cost_anomalies(
        points=spike_points,
        start_date="2026-10-01",
        end_date="2026-10-09",
        threshold=2.0,
    )
    assert len(anomalies_spiked.anomalies) >= 1
    assert anomalies_spiked.anomalies[0].date == "2026-10-08"
    assert anomalies_spiked.anomalies[0].amount == 100.0


def test_cost_attribution_service_and_rejection():
    client = MagicMock()
    client.get_service_costs.return_value = [
        AWSServiceCost(service="Amazon S3", amount=5.0, start_date="2026-10-01", end_date="2026-10-10"),
        AWSServiceCost(service="Amazon EC2", amount=25.0, start_date="2026-10-01", end_date="2026-10-10"),
    ]
    service = AWSFinOpsService(client=client)

    attribution = service.get_cost_attribution(
        start_date="2026-10-01",
        end_date="2026-10-10",
        dimension="service",
    )
    assert attribution.total_cost == 30.0
    assert len(attribution.entries) == 2
    # Verify sorted descending by amount
    assert attribution.entries[0].value == "Amazon EC2"
    assert attribution.entries[0].amount == 25.0
    assert attribution.entries[1].value == "Amazon S3"
    assert attribution.entries[1].amount == 5.0

    # Invalid dimension raises ValueError
    with pytest.raises(ValueError, match="Unsupported dimension"):
        service.get_cost_attribution(
            start_date="2026-10-01",
            end_date="2026-10-10",
            dimension="unsupported_dim",
        )


def test_get_budgets_status_and_utilization():
    client = MagicMock()
    client.get_account_id.return_value = "111122223333"
    client.get_budgets.return_value = [
        {
            "BudgetName": "DevBudget",
            "BudgetType": "COST",
            "TimeUnit": "MONTHLY",
            "BudgetLimit": {"Amount": "100.0", "Unit": "USD"},
            "CalculatedSpend": {
                "ActualSpend": {"Amount": "50.0", "Unit": "USD"},
                "ForecastedSpend": {"Amount": "80.0", "Unit": "USD"},
            },
            "CostFilters": {},
        },
        {
            "BudgetName": "OverspendBudget",
            "BudgetType": "COST",
            "TimeUnit": "MONTHLY",
            "BudgetLimit": {"Amount": "100.0", "Unit": "USD"},
            "CalculatedSpend": {
                "ActualSpend": {"Amount": "110.0", "Unit": "USD"},
            },
            "CostFilters": {},
        },
    ]
    service = AWSFinOpsService(client=client)

    budgets_resp = service.get_budgets()
    assert budgets_resp.account_id == "111122223333"
    assert len(budgets_resp.budgets) == 2

    b1 = budgets_resp.budgets[0]
    assert b1.name == "DevBudget"
    assert b1.actual_utilization_percent == 50.0
    assert b1.status == BudgetStatus.HEALTHY

    b2 = budgets_resp.budgets[1]
    assert b2.name == "OverspendBudget"
    assert b2.actual_utilization_percent == 110.0
    assert b2.status == BudgetStatus.BREACHED


def test_aws_client_error_propagation():
    client = MagicMock()
    client.collect_snapshot.side_effect = AWSFinOpsError("AccessDeniedException: User is not authorized")

    service = AWSFinOpsService(client=client)
    with pytest.raises(AWSFinOpsError, match="AccessDeniedException"):
        service.generate_report(start_date="2026-10-01", end_date="2026-10-08")


def test_report_data_source_explicit_tagging():
    client = MagicMock()
    client.collect_snapshot.return_value = AWSFinOpsSnapshot(
        account_id="999888777666",
        region="us-east-1",
        cost_start_date="2026-10-01",
        cost_end_date="2026-10-08",
        service_costs=[],
        resources=[],
    )
    service = AWSFinOpsService(client=client)
    report = service.generate_report(start_date="2026-10-01", end_date="2026-10-08")

    assert report.cost_data_source == "aws-cost-explorer"
    assert report.account_id == "999888777666"
    assert report.summary.total_estimated_monthly_cost == 0.0


def test_generate_report_distinguishes_actual_and_unavailable_costs():
    client = MagicMock()
    client.collect_snapshot.return_value = AWSFinOpsSnapshot(
        account_id="123456789012",
        region="eu-west-1",
        cost_start_date="2026-10-01",
        cost_end_date="2026-10-08",
        service_costs=[
            AWSServiceCost(
                service="Amazon EC2",
                amount=75.50,
                start_date="2026-10-01",
                end_date="2026-10-08",
            ),
            AWSServiceCost(
                service="Amazon S3",
                amount=14.20,
                start_date="2026-10-01",
                end_date="2026-10-08",
            ),
        ],
        resources=[
            AWSResource(
                resource_arn="arn:aws:ec2:eu-west-1:123456789012:instance/i-0abcdef1234567890",
                resource_type=ResourceType.EC2,
                service="ec2",
                region="eu-west-1",
                tags={"Environment": "production"},
            ),
            AWSResource(
                resource_arn="arn:aws:s3:::my-untracked-bucket",
                resource_type=ResourceType.S3,
                service="s3",
                region="eu-west-1",
                tags={},
            ),
        ],
    )
    service = AWSFinOpsService(client=client)
    report = service.generate_report(start_date="2026-10-01", end_date="2026-10-08")

    # 1. Misleading hardcoded 0.0 and False must be removed
    for res in report.resources:
        assert res["estimated_monthly_cost"] is None
        assert res["cost_status"] == "unavailable"
        assert res["idle"] is None
        assert res["utilization_status"] == "unavailable"

    # 2. Actual costs from Cost Explorer are preserved
    assert len(report.service_costs) == 2
    assert report.summary.total_actual_monthly_cost == 89.70

    # 3. Summary counters accurately reflect unavailable data
    assert report.summary.unavailable_cost_count == 2
    assert report.summary.unavailable_utilization_count == 2
    assert report.summary.total_estimated_monthly_cost == 0.0


def test_missing_costs_and_metrics_in_analyzer():
    from .finops_analyzer import FinOpsAnalyzer

    analyzer = FinOpsAnalyzer()
    report = analyzer.analyze(
        region="eu-west-1",
        account_id="111122223333",
        resources=[
            {
                "resource_id": "res-untracked",
                "resource_type": "ec2",
                "service": "ec2",
                # missing estimated_monthly_cost and idle
                "tags": {"Environment": "prod"},
            },
            {
                "resource_id": "res-known-estimate",
                "resource_type": "ec2",
                "service": "ec2",
                "estimated_monthly_cost": 45.0,
                "idle": False,
                "tags": {"Environment": "prod"},
            },
        ],
    )

    assert report.summary.findings_count == 2
    f1 = report.findings[0]
    assert f1.estimated_monthly_cost is None
    assert f1.cost_status == "unavailable"
    assert f1.idle is None
    assert f1.utilization_status == "unavailable"

    f2 = report.findings[1]
    assert f2.estimated_monthly_cost == 45.0
    assert f2.cost_status == "estimated"
    assert f2.idle is False
    assert f2.utilization_status == "observed"

    assert report.summary.total_estimated_monthly_cost == 45.0
    assert report.summary.unavailable_cost_count == 1
    assert report.summary.unavailable_utilization_count == 1


def test_cost_attribution_resource_dimension_unavailable():
    client = MagicMock()
    client.get_resource_costs.side_effect = AWSFinOpsError(
        "Hourly and Resource Level Data is not enabled"
    )
    service = AWSFinOpsService(client=client)

    attribution = service.get_cost_attribution(
        start_date="2026-10-01",
        end_date="2026-10-08",
        dimension="resource_id",
    )

    assert attribution.available is False
    assert attribution.total_cost == 0.0
    assert attribution.entries == []
    assert "Resource-level cost attribution is unavailable" in attribution.status_message


def test_cost_attribution_resource_dimension_success():
    client = MagicMock()
    client.get_resource_costs.return_value = [
        {"resource_id": "i-0abcdef1234567890", "amount": 25.5, "currency": "USD"},
        {"resource_id": "vol-0123456789abcdef0", "amount": 10.2, "currency": "USD"},
    ]
    service = AWSFinOpsService(client=client)

    attribution = service.get_cost_attribution(
        start_date="2026-10-01",
        end_date="2026-10-08",
        dimension="resource_id",
    )

    assert attribution.available is True
    assert attribution.total_cost == 35.7
    assert len(attribution.entries) == 2
    assert attribution.entries[0].value == "i-0abcdef1234567890"
    assert attribution.entries[0].amount == 25.5


def test_cloudwatch_ec2_cpu_utilization_success():
    client = AWSFinOpsClient.__new__(AWSFinOpsClient)
    client.region = "eu-west-1"
    mock_cw = MagicMock()
    mock_cw.get_metric_statistics.return_value = {
        "Datapoints": [
            {"Average": 12.0, "Unit": "Percent"},
            {"Average": 16.0, "Unit": "Percent"},
        ]
    }
    client.cloudwatch = mock_cw

    result = client.get_ec2_cpu_utilization(
        instance_id="i-0abcdef1234567890",
        start_time="2026-10-01T00:00:00Z",
        end_time="2026-10-08T00:00:00Z",
        period_seconds=3600,
    )

    assert result["utilization_available"] is True
    assert result["cpu_utilization_percent"] == 14.0
    assert result["datapoints_count"] == 2
    assert result["unit"] == "Percent"
    assert result["period_seconds"] == 3600

    # Verify query parameters
    call_kwargs = mock_cw.get_metric_statistics.call_args[1]
    assert call_kwargs["Namespace"] == "AWS/EC2"
    assert call_kwargs["MetricName"] == "CPUUtilization"
    assert call_kwargs["Dimensions"] == [{"Name": "InstanceId", "Value": "i-0abcdef1234567890"}]
    assert call_kwargs["Unit"] == "Percent"
    assert call_kwargs["Period"] == 3600


def test_cloudwatch_ec2_cpu_utilization_missing_data():
    client = AWSFinOpsClient.__new__(AWSFinOpsClient)
    client.region = "eu-west-1"
    mock_cw = MagicMock()
    mock_cw.get_metric_statistics.return_value = {"Datapoints": []}
    client.cloudwatch = mock_cw

    result = client.get_ec2_cpu_utilization(
        instance_id="i-stopped-instance",
        start_time="2026-10-01T00:00:00Z",
        end_time="2026-10-08T00:00:00Z",
    )

    assert result["utilization_available"] is False
    assert result["cpu_utilization_percent"] is None
    assert result["datapoints_count"] == 0
    assert "No CloudWatch metric datapoints found" in result["reason"]


def test_collect_ec2_optimization_observations_with_cloudwatch():
    client = MagicMock()
    client.collect_snapshot.return_value = AWSFinOpsSnapshot(
        account_id="123456789012",
        region="eu-west-1",
        cost_start_date="2026-10-01",
        cost_end_date="2026-10-08",
        service_costs=[],
        resources=[
            AWSResource(
                resource_arn="arn:aws:ec2:eu-west-1:123456789012:instance/i-0abcdef1234567890",
                resource_type=ResourceType.EC2,
                service="ec2",
                region="eu-west-1",
                tags={},
            ),
            AWSResource(
                resource_arn="arn:aws:s3:::some-bucket",
                resource_type=ResourceType.S3,
                service="s3",
                region="eu-west-1",
                tags={},
            ),
        ],
    )
    client.get_ec2_cpu_utilization.return_value = {
        "cpu_utilization_percent": 15.5,
        "utilization_available": True,
        "datapoints_count": 24,
    }

    service = AWSFinOpsService(client=client)
    observations = service.collect_ec2_optimization_observations()

    assert len(observations) == 1
    obs = observations[0]
    assert obs.resource_id == "i-0abcdef1234567890"
    assert obs.cpu_utilization_percent == 15.5
    assert obs.utilization_available is True
    assert obs.datapoints_count == 24


def test_no_deletion_recommendation_without_supporting_cost_and_utilization():
    from .finops_analyzer import FinOpsAnalyzer

    analyzer = FinOpsAnalyzer()

    # 1. Resource marked idle but without cost evidence
    rep1 = analyzer.analyze(
        region="eu-west-1",
        resources=[
            {
                "resource_id": "i-idle-nocost",
                "resource_type": "ec2",
                "service": "ec2",
                "idle": True,
                "tags": {"Env": "dev"},
            }
        ],
    )
    f1 = rep1.findings[0]
    assert "delete" not in f1.recommendation.lower()
    assert "Verify resource-level cost evidence" in f1.recommendation

    # 2. Resource with unobserved utilization (idle is None)
    rep2 = analyzer.analyze(
        region="eu-west-1",
        resources=[
            {
                "resource_id": "i-unobserved",
                "resource_type": "ec2",
                "service": "ec2",
                "tags": {"Env": "dev"},
            }
        ],
    )
    f2 = rep2.findings[0]
    assert "delete" not in f2.recommendation.lower()
    assert f2.idle is None
    assert f2.utilization_status == "unavailable"


def test_default_ec2_observation_no_metrics():
    from .finops_optimization_models import EC2Observation

    obs = EC2Observation(
        resource_id="i-default-123",
        instance_type="t3.large",
    )
    assert obs.utilization_available is False
    assert obs.cpu_utilization_percent is None
    assert obs.datapoints_count is None


def test_default_kubernetes_workload_no_metrics():
    from .finops_optimization_models import KubernetesWorkload

    workload = KubernetesWorkload(
        namespace="default",
        workload="payment-service",
    )
    assert workload.cpu_usage_available is False
    assert workload.memory_usage_available is False
    assert workload.cpu_usage_cores == 0.0
    assert workload.memory_usage_bytes == 0.0


def test_missing_cpu_and_memory_observations():
    from .finops_optimization_engine import FinOpsOptimizationEngine
    from .finops_optimization_models import (
        KubernetesOptimizationSnapshot,
        KubernetesWorkload,
        NodeObservation,
    )

    engine = FinOpsOptimizationEngine()
    snapshot = KubernetesOptimizationSnapshot(
        workloads=[
            KubernetesWorkload(
                namespace="prod",
                workload="api",
                replicas=3,
                cpu_request_cores=4.0,
                memory_request_bytes=8 * 1024**3,
                cpu_usage_available=False,
                memory_usage_available=False,
            )
        ],
        nodes=[
            NodeObservation(
                node="ip-10-0-1-5",
                cpu_allocatable_cores=8,
                cpu_requested_cores=2,
                cpu_usage_cores=0.0,
                memory_allocatable_bytes=16 * 1024**3,
                memory_requested_bytes=4 * 1024**3,
                memory_usage_bytes=0.0,
                cpu_usage_available=False,
                memory_usage_available=False,
            )
        ],
    )

    report = engine.build_report(kubernetes=snapshot)
    problematic_metrics = {
        "cpu_request_vs_usage",
        "memory_request_vs_usage",
        "workload_utilization",
        "node_cpu_utilization",
        "node_memory_utilization",
    }
    generated_metrics = {f.metric for f in report.findings}
    assert not (problematic_metrics & generated_metrics)


def test_valid_observations_explicitly_marked_available():
    from .finops_optimization_engine import FinOpsOptimizationEngine
    from .finops_optimization_models import (
        AWSOptimizationObservation,
        EC2Observation,
        KubernetesOptimizationSnapshot,
        KubernetesWorkload,
    )

    engine = FinOpsOptimizationEngine()
    snapshot = KubernetesOptimizationSnapshot(
        workloads=[
            KubernetesWorkload(
                namespace="prod",
                workload="api",
                replicas=2,
                cpu_request_cores=4.0,
                cpu_usage_cores=0.2,
                cpu_usage_available=True,
                memory_request_bytes=8 * 1024**3,
                memory_usage_bytes=100 * 1024**2,
                memory_usage_available=True,
            )
        ]
    )
    aws_obs = AWSOptimizationObservation(
        ec2=[
            EC2Observation(
                resource_id="i-0123456789abcdef0",
                instance_type="m5.xlarge",
                cpu_utilization_percent=5.0,
                utilization_available=True,
                monthly_cost_usd=140.0,
                target_instance_type="m5.large",
                target_monthly_cost_usd=70.0,
            )
        ]
    )

    report = engine.build_report(kubernetes=snapshot, aws=aws_obs)
    metrics = {f.metric for f in report.findings}
    assert "cpu_request_vs_usage" in metrics
    assert "memory_request_vs_usage" in metrics
    assert "cpu_utilization_percent" in metrics


def test_no_idle_recommendation_when_telemetry_unavailable():
    from .finops_optimization_engine import FinOpsOptimizationEngine
    from .finops_optimization_models import (
        KubernetesOptimizationSnapshot,
        KubernetesWorkload,
    )

    engine = FinOpsOptimizationEngine()
    snapshot = KubernetesOptimizationSnapshot(
        workloads=[
            KubernetesWorkload(
                namespace="prod",
                workload="backend",
                replicas=3,
                cpu_usage_cores=0.0,
                memory_usage_bytes=0.0,
                cpu_usage_available=False,
                memory_usage_available=False,
            )
        ]
    )

    report = engine.build_report(kubernetes=snapshot)
    metrics = [f.metric for f in report.findings]
    assert "workload_utilization" not in metrics
