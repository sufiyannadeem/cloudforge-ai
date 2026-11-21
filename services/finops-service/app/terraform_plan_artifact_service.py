from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from pydantic import ValidationError

from .terraform_cost_models import (
    TerraformPricingEvidence,
)
from .terraform_plan_artifact_models import (
    TerraformPlanArtifact,
    TerraformPlanArtifactCostResponse,
    TerraformPlanEvidenceCoverage,
)
from .terraform_plan_cost_service import (
    TerraformPlanCostService,
)
from .terraform_plan_parser import (
    TerraformPlanParser,
)


class TerraformPlanArtifactService:
    """
    Validates and fingerprints externally-produced Terraform
    show -json artifacts, then sends the validated plan through
    the existing deterministic parser and cost estimator.

    Safety guarantees:

    - Terraform is never executed.
    - AWS APIs are never called.
    - Pricing APIs are never called.
    - Infrastructure is never mutated.
    - Pricing must be supplied as explicit evidence.
    """

    def __init__(
        self,
        parser: TerraformPlanParser | None = None,
        cost_service: TerraformPlanCostService | None = None,
    ) -> None:
        self.parser = parser or TerraformPlanParser()
        self.cost_service = (
            cost_service or TerraformPlanCostService()
        )

    def create_artifact(
        self,
        *,
        plan: dict[str, Any],
        source: str,
        workspace: str,
        environment: str,
        region: str,
        artifact_id: str | None = None,
    ) -> TerraformPlanArtifact:
        self._validate_plan_structure(plan)

        resource_changes = plan["resource_changes"]

        return TerraformPlanArtifact(
            artifact_id=(
                artifact_id.strip()
                if artifact_id
                else str(uuid.uuid4())
            ),
            source=source,
            workspace=workspace,
            environment=environment,
            region=region,
            resource_count=len(resource_changes),
            plan_hash=self._hash_plan(plan),
        )

    def estimate(
        self,
        *,
        plan: dict[str, Any],
        source: str,
        workspace: str,
        environment: str,
        region: str,
        pricing: dict[str, TerraformPricingEvidence] | None = None,
        artifact_id: str | None = None,
    ) -> TerraformPlanArtifactCostResponse:
        artifact = self.create_artifact(
            plan=plan,
            source=source,
            workspace=workspace,
            environment=environment,
            region=region,
            artifact_id=artifact_id,
        )

        result = self.cost_service.estimate(
            plan=plan,
            pricing=pricing or {},
        )

        report = result.cost_report

        priced_resource_count = sum(
            1
            for estimate in report.estimates
            if estimate.evidence_available
        )

        parsed_resource_count = len(report.estimates)

        missing_pricing_resource_count = max(
            parsed_resource_count
            - priced_resource_count,
            0,
        )

        if parsed_resource_count:
            coverage_percent = (
                priced_resource_count
                / parsed_resource_count
                * 100
            )
        else:
            coverage_percent = 100.0

        coverage = TerraformPlanEvidenceCoverage(
            parsed_resource_count=parsed_resource_count,
            priced_resource_count=priced_resource_count,
            missing_pricing_resource_count=(
                missing_pricing_resource_count
            ),
            coverage_percent=coverage_percent,
            complete=(
                parsed_resource_count == priced_resource_count
            ),
        )

        return TerraformPlanArtifactCostResponse(
            artifact=artifact,
            cost_report=report,
            parse_issues=[
                issue.message
                for issue in result.parse_result.issues
            ],
            unsupported_resources=result.parse_result.unsupported_resources,
            parsed_resource_count=parsed_resource_count,
            evidence_coverage=coverage,
        )

    @staticmethod
    def _validate_plan_structure(
        plan: dict[str, Any],
    ) -> None:
        if not isinstance(plan, dict):
            raise ValueError(
                "Terraform plan must be a JSON object."
            )

        resource_changes = plan.get("resource_changes")

        if resource_changes is None:
            raise ValueError(
                "Terraform plan is missing resource_changes."
            )

        if not isinstance(resource_changes, list):
            raise ValueError(
                "Terraform plan resource_changes must be an array."
            )

        for index, resource in enumerate(
            resource_changes
        ):
            if not isinstance(resource, dict):
                raise ValueError(
                    "Terraform plan resource_changes "
                    f"[{index}] must be an object."
                )

            address = resource.get("address")

            if not isinstance(address, str) or not address.strip():
                raise ValueError(
                    "Terraform plan resource_changes "
                    f"[{index}] is missing a valid address."
                )

            resource_type = resource.get("type")

            if not isinstance(resource_type, str) or not resource_type.strip():
                raise ValueError(
                    "Terraform plan resource_changes "
                    f"[{index}] is missing a valid type."
                )

            change = resource.get("change")

            if not isinstance(change, dict):
                raise ValueError(
                    "Terraform plan resource_changes "
                    f"[{index}] is missing a valid change object."
                )

            actions = change.get("actions")

            if not isinstance(actions, list):
                raise ValueError(
                    "Terraform plan resource_changes "
                    f"[{index}] change.actions must be an array."
                )

    @staticmethod
    def _hash_plan(
        plan: dict[str, Any],
    ) -> str:
        canonical = json.dumps(
            plan,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
