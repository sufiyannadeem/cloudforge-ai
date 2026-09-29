from __future__ import annotations

from .finops_optimization_engine import (
    FinOpsOptimizationEngine,
)
from .finops_optimization_models import (
    AWSOptimizationObservation,
    OptimizationReport,
)
from .finops_optimization_prometheus import (
    PrometheusFinOpsCollector,
)


class FinOpsOptimizationService:
    def __init__(
        self,
        *,
        engine: FinOpsOptimizationEngine | None = None,
        prometheus: PrometheusFinOpsCollector | None = None,
    ) -> None:
        self.engine = (
            engine
            if engine is not None
            else FinOpsOptimizationEngine()
        )

        self.prometheus = (
            prometheus
            if prometheus is not None
            else PrometheusFinOpsCollector()
        )

    def analyze_kubernetes(
        self,
    ) -> OptimizationReport:
        snapshot = self.prometheus.collect_snapshot()

        return self.engine.build_report(
            kubernetes=snapshot
        )

    def analyze_aws(
        self,
        observation: AWSOptimizationObservation,
    ) -> OptimizationReport:
        return self.engine.build_report(
            aws=observation
        )

    def analyze_all(
        self,
        observation: AWSOptimizationObservation | None = None,
    ) -> OptimizationReport:
        snapshot = self.prometheus.collect_snapshot()

        return self.engine.build_report(
            kubernetes=snapshot,
            aws=observation,
        )
