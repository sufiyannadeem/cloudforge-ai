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
        )

        idle_cost = sum(
            finding.estimated_monthly_cost
            for finding in findings
            if finding.idle
        )

        summary = CostSummary(
            total_estimated_monthly_cost=round(
                total_cost,
                2,
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

        estimated_cost = float(
            resource.get(
                "estimated_monthly_cost",
                0.0,
            )
            or 0.0
        )

        idle = bool(
            resource.get(
                "idle",
                False,
            )
        )

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

        if idle and estimated_cost >= 50:
            severity = CostSeverity.CRITICAL

        elif idle or estimated_cost >= 100:
            severity = CostSeverity.WARNING

        if idle:
            reason = (
                "Resource is marked idle and has "
                "estimated ongoing monthly cost."
            )

            recommendation = (
                "Review whether the resource is still "
                "required before the next billing cycle."
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
            severity=severity,
            idle=idle,
            untagged=untagged,
            region=resource.get("region"),
            tags={
                str(key): str(value)
                for key, value in tags.items()
            },
            reason=reason,
            recommendation=recommendation,
        )
