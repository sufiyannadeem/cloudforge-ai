from __future__ import annotations

from .terraform_cost_policy_models import (
    TerraformCostComparison,
    TerraformCostPolicy,
    TerraformCostPolicyDecision,
    TerraformCostPolicyEvaluation,
)
from .terraform_plan_cost_service import TerraformPlanCostResult


class TerraformCostPolicyService:
    """
    Deterministic financial policy evaluation.

    This service does not execute Terraform, call AWS, retrieve pricing,
    mutate infrastructure, or use AI to make policy decisions.
    """

    GENERATED_BY = "cloudforge-finops-cost-policy-v1"

    @staticmethod
    def compare(
        result: TerraformPlanCostResult,
    ) -> TerraformCostComparison:
        report = result.cost_report

        current = report.total_current_monthly_usd
        proposed = report.total_proposed_monthly_usd
        delta = report.total_monthly_delta_usd

        if current > 0:
            delta_percent = (delta / current) * 100
        elif proposed > 0:
            delta_percent = None
        else:
            delta_percent = 0.0

        return TerraformCostComparison(
            current_monthly_usd=current,
            proposed_monthly_usd=proposed,
            monthly_delta_usd=delta,
            monthly_delta_percent=delta_percent,
            evidence_complete=report.evidence_complete,
            resource_count=report.resource_count,
        )

    @classmethod
    def evaluate(
        cls,
        result: TerraformPlanCostResult,
        policy: TerraformCostPolicy,
    ) -> TerraformCostPolicyEvaluation:
        comparison = cls.compare(result)
        reasons: list[str] = []

        if not comparison.evidence_complete:
            reasons.append(
                "Pricing evidence is incomplete for one or more resources."
            )

            if policy.block_if_evidence_incomplete:
                reasons.append(
                    "Policy blocks changes when pricing evidence is incomplete."
                )
                return TerraformCostPolicyEvaluation(
                    decision=TerraformCostPolicyDecision.BLOCK,
                    reasons=reasons,
                    comparison=comparison,
                    policy=policy,
                    generated_by=cls.GENERATED_BY,
                )

            if policy.review_if_evidence_incomplete:
                reasons.append(
                    "Policy requires human review when pricing evidence is incomplete."
                )
                return TerraformCostPolicyEvaluation(
                    decision=TerraformCostPolicyDecision.REVIEW,
                    reasons=reasons,
                    comparison=comparison,
                    policy=policy,
                    generated_by=cls.GENERATED_BY,
                )

        delta = comparison.monthly_delta_usd

        if delta <= 0:
            reasons.append(
                "The proposed configuration does not increase monthly cost."
            )
            return TerraformCostPolicyEvaluation(
                decision=TerraformCostPolicyDecision.ALLOW,
                reasons=reasons,
                comparison=comparison,
                policy=policy,
                generated_by=cls.GENERATED_BY,
            )

        if delta > policy.max_monthly_increase_usd:
            reasons.append(
                "Monthly cost increase exceeds the configured USD threshold."
            )
            return TerraformCostPolicyEvaluation(
                decision=TerraformCostPolicyDecision.BLOCK,
                reasons=reasons,
                comparison=comparison,
                policy=policy,
                generated_by=cls.GENERATED_BY,
            )

        if (
            comparison.monthly_delta_percent is not None
            and comparison.monthly_delta_percent
            > policy.max_monthly_increase_percent
        ):
            reasons.append(
                "Monthly cost increase exceeds the configured percentage threshold."
            )
            return TerraformCostPolicyEvaluation(
                decision=TerraformCostPolicyDecision.REVIEW,
                reasons=reasons,
                comparison=comparison,
                policy=policy,
                generated_by=cls.GENERATED_BY,
            )

        reasons.append(
            "Monthly cost increase is within the configured policy thresholds."
        )

        return TerraformCostPolicyEvaluation(
            decision=TerraformCostPolicyDecision.ALLOW,
            reasons=reasons,
            comparison=comparison,
            policy=policy,
            generated_by=cls.GENERATED_BY,
        )
