from __future__ import annotations

from .terraform_cost_models import (
    TerraformChangeAction,
    TerraformCostEstimate,
    TerraformCostEstimateReport,
    TerraformResourceChange,
)


class TerraformCostEstimator:
    """
    Deterministic Terraform cost estimator.

    The estimator deliberately does not:
    - execute Terraform;
    - call AWS;
    - query external pricing APIs;
    - infer market prices;
    - mutate infrastructure.

    Pricing must be explicitly supplied as evidence by the caller.
    """

    GENERATED_BY = "cloudforge-finops-terraform-cost-v1"

    def estimate(
        self,
        changes: list[TerraformResourceChange],
    ) -> TerraformCostEstimateReport:
        estimates = [self.estimate_change(change) for change in changes]

        total_current = round(
            sum(item.current_monthly_usd for item in estimates),
            6,
        )
        total_proposed = round(
            sum(item.proposed_monthly_usd for item in estimates),
            6,
        )
        total_delta = round(total_proposed - total_current, 6)

        evidence_complete = all(
            item.evidence_available for item in estimates
        )

        return TerraformCostEstimateReport(
            estimates=estimates,
            total_current_monthly_usd=total_current,
            total_proposed_monthly_usd=total_proposed,
            total_monthly_delta_usd=total_delta,
            evidence_complete=evidence_complete,
            resource_count=len(estimates),
            generated_by=self.GENERATED_BY,
        )

    def estimate_change(
        self,
        change: TerraformResourceChange,
    ) -> TerraformCostEstimate:
        pricing = change.pricing

        if pricing is None or not pricing.evidence_available:
            return self._without_pricing(change)

        unit_price = pricing.unit_monthly_usd

        current = round(
            change.current_quantity * unit_price,
            6,
        )
        proposed = round(
            change.proposed_quantity * unit_price,
            6,
        )
        delta = round(proposed - current, 6)

        calculation = (
            f"current: {change.current_quantity:g} × "
            f"${unit_price:.6f} = ${current:.6f}/month; "
            f"proposed: {change.proposed_quantity:g} × "
            f"${unit_price:.6f} = ${proposed:.6f}/month; "
            f"delta: ${delta:.6f}/month"
        )

        assumptions = list(pricing.assumptions)

        if change.action is TerraformChangeAction.CREATE:
            assumptions.append(
                "Create is modeled as proposed quantity minus zero."
            )
        elif change.action is TerraformChangeAction.DELETE:
            assumptions.append(
                "Delete is modeled as zero proposed quantity."
            )
        elif change.action is TerraformChangeAction.UPDATE:
            assumptions.append(
                "Update uses the supplied pricing evidence for both quantities."
            )
        else:
            assumptions.append(
                "No-op retains the supplied current and proposed quantities."
            )

        return TerraformCostEstimate(
            resource_type=change.resource_type,
            resource_id=change.resource_id,
            action=change.action,
            region=change.region,
            current_monthly_usd=current,
            proposed_monthly_usd=proposed,
            monthly_delta_usd=delta,
            pricing_source=pricing.source,
            confidence=pricing.confidence,
            evidence_available=True,
            calculation=calculation,
            assumptions=assumptions,
        )

    def _without_pricing(
        self,
        change: TerraformResourceChange,
    ) -> TerraformCostEstimate:
        return TerraformCostEstimate(
            resource_type=change.resource_type,
            resource_id=change.resource_id,
            action=change.action,
            region=change.region,
            current_monthly_usd=0.0,
            proposed_monthly_usd=0.0,
            monthly_delta_usd=0.0,
            pricing_source=(
                change.pricing.source
                if change.pricing is not None
                else None
            ),
            confidence=(
                change.pricing.confidence
                if change.pricing is not None
                else "unknown"
            ),
            evidence_available=False,
            calculation=(
                "Cost not estimated: required pricing evidence "
                "is unavailable."
            ),
            assumptions=[
                "No external cloud pricing was inferred.",
                "Zero cost here means unknown cost, not confirmed zero cost.",
            ],
        )
