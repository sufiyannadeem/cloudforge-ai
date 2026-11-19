from __future__ import annotations


from .finops_models import (
    CostFinding,
    CostSeverity,
    CostSummary,
    FinOpsReport,
    ResourceType,
)


class FinOpsAnalyzer:
    """
    Deterministic FinOps analysis engine.

    This layer does not use an LLM.

    Its job is to establish factual cost/resource
    findings before AI interpretation.
    """

    def analyze(
        self,
        *,
        region: str,
        resources: list[dict],
        account_id: str | None = None,
    ) -> FinOpsReport:

        findings: list[CostFinding] = []

        for resource in resources:
            finding = self._analyze_resource(
                resource
            )

            if finding is not None:
                findings.append(finding)

        total_cost = sum(
            finding.estimated_monthly_cost
            for finding in findings
            if finding.estimated_monthly_cost is not None
        )

        total_actual = sum(
            finding.actual_monthly_cost
            for finding in findings
            if finding.actual_monthly_cost is not None
        )

        idle_cost = sum(
            finding.estimated_monthly_cost
            for finding in findings
            if finding.idle is True and finding.estimated_monthly_cost is not None
        )

        unavailable_cost_count = sum(
            1 for finding in findings if finding.cost_status == "unavailable"
        )

        unavailable_util_count = sum(
            1 for finding in findings if finding.utilization_status == "unavailable"
        )

        summary = CostSummary(
            total_estimated_monthly_cost=round(
                total_cost,
                2,
            ),
            total_actual_monthly_cost=(
                round(total_actual, 2)
                if any(f.actual_monthly_cost is not None for f in findings)
                else None
            ),
            idle_monthly_cost=round(
                idle_cost,
                2,
            ),
            untagged_resource_count=sum(
                1
                for finding in findings
                if finding.untagged
            ),
            findings_count=len(findings),
            critical_findings=sum(
                1
                for finding in findings
                if finding.severity
                == CostSeverity.CRITICAL
            ),
            warning_findings=sum(
                1
                for finding in findings
                if finding.severity
                == CostSeverity.WARNING
            ),
            info_findings=sum(
                1
                for finding in findings
                if finding.severity
                == CostSeverity.INFO
            ),
            unavailable_cost_count=unavailable_cost_count,
            unavailable_utilization_count=unavailable_util_count,
        )

        return FinOpsReport(
            account_id=account_id,
            region=region,
            summary=summary,
            findings=findings,
        )

    def _analyze_resource(
        self,
        resource: dict,
    ) -> CostFinding | None:

        resource_id = str(
            resource.get(
                "resource_id",
                "",
            )
        ).strip()

        if not resource_id:
            return None

        raw_resource_type = str(
            resource.get(
                "resource_type",
                "unknown",
            )
        ).strip().lower()

        try:
            resource_type = ResourceType(
                raw_resource_type
            )
        except ValueError:
            resource_type = ResourceType.UNKNOWN

        service = str(
            resource.get(
                "service",
                resource_type,
            )
        ).strip()

        raw_estimated_cost = resource.get("estimated_monthly_cost")
        raw_actual_cost = resource.get("actual_monthly_cost")
        cost_status = resource.get("cost_status")

        if raw_actual_cost is not None:
            actual_cost = float(raw_actual_cost)
            estimated_cost = actual_cost
            cost_status = "actual"
        elif raw_estimated_cost is not None:
            actual_cost = None
            estimated_cost = float(raw_estimated_cost)
            cost_status = cost_status or "estimated"
        else:
            actual_cost = None
            estimated_cost = None
            cost_status = "unavailable"

        raw_idle = resource.get("idle")
        utilization_status = resource.get("utilization_status")

        if raw_idle is not None:
            idle = bool(raw_idle)
            utilization_status = utilization_status or "observed"
        else:
            idle = None
            utilization_status = "unavailable"

        tags = resource.get(
            "tags",
            {},
        )

        if not isinstance(
            tags,
            dict,
        ):
            tags = {}

        untagged = len(tags) == 0

        severity = CostSeverity.INFO

        if idle is True and estimated_cost is not None and estimated_cost >= 50:
            severity = CostSeverity.CRITICAL

        elif idle is True or (estimated_cost is not None and estimated_cost >= 100):
            severity = CostSeverity.WARNING

        if idle is True:
            if estimated_cost is not None and estimated_cost > 0:
                reason = (
                    "Resource is marked idle with observed low/zero utilization "
                    "and has estimated ongoing monthly cost."
                )

                recommendation = (
                    "Review whether the resource is still required before the next billing cycle; "
                    "verify workload needs and plan decommission or rightsizing with team approval."
                )
            else:
                reason = (
                    "Resource is observed idle, but reliable cost data is unavailable."
                )

                recommendation = (
                    "Verify resource-level cost evidence before taking decommission or rightsizing action."
                )

        elif idle is None:
            if untagged:
                reason = (
                    "Resource has no cost-allocation tags; utilization and cost evidence are unavailable."
                )

                recommendation = (
                    "Apply CloudForge ownership, environment and cost-center tags; "
                    "attach telemetry to observe utilization."
                )
            else:
                reason = (
                    "Resource has no deterministic cost optimization finding; "
                    "utilization telemetry is not observed."
                )

                recommendation = (
                    "Continue monitoring usage and cost; attach telemetry to observe utilization."
                )

        elif untagged:
            reason = (
                "Resource has no cost-allocation tags."
            )

            recommendation = (
                "Apply CloudForge ownership, environment "
                "and cost-center tags."
            )

        else:
            reason = (
                "Resource has no deterministic cost "
                "optimization finding."
            )

            recommendation = (
                "Continue monitoring usage and cost."
            )

        return CostFinding(
            resource_id=resource_id,
            resource_type=resource_type,
            service=service,
            estimated_monthly_cost=estimated_cost,
            actual_monthly_cost=actual_cost,
            cost_status=cost_status,
            severity=severity,
            idle=idle,
            utilization_status=utilization_status,
            untagged=untagged,
            region=resource.get("region"),
            tags={
                str(key): str(value)
                for key, value in tags.items()
            },
            reason=reason,
            recommendation=recommendation,
        )
