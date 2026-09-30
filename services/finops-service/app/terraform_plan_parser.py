from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from .terraform_cost_models import (
    TerraformChangeAction,
    TerraformResourceChange,
    TerraformResourceType,
)


class TerraformPlanParseIssue(BaseModel):
    resource_address: str | None = None
    message: str


class TerraformPlanParseResult(BaseModel):
    changes: list[TerraformResourceChange] = Field(default_factory=list)
    issues: list[TerraformPlanParseIssue] = Field(default_factory=list)
    unsupported_resources: list[str] = Field(default_factory=list)
    resource_count: int = 0


class TerraformPlanParser:
    """
    Converts Terraform plan JSON resource_changes into the normalized
    TerraformResourceChange model used by the FinOps cost estimator.

    This parser:
    - does not execute Terraform;
    - does not call AWS;
    - does not query pricing APIs;
    - does not infer cloud prices;
    - does not mutate infrastructure.

    Pricing evidence must be supplied separately.
    """

    SUPPORTED_RESOURCE_TYPES = {
        resource_type.value: resource_type
        for resource_type in TerraformResourceType
    }

    def parse(
        self,
        plan: Mapping[str, Any],
    ) -> TerraformPlanParseResult:
        issues: list[TerraformPlanParseIssue] = []
        changes: list[TerraformResourceChange] = []
        unsupported_resources: list[str] = []

        resource_changes = plan.get("resource_changes", [])

        if resource_changes is None:
            resource_changes = []

        if not isinstance(resource_changes, list):
            return TerraformPlanParseResult(
                issues=[
                    TerraformPlanParseIssue(
                        message="Terraform plan field 'resource_changes' must be a list."
                    )
                ]
            )

        for resource_change in resource_changes:
            if not isinstance(resource_change, Mapping):
                issues.append(
                    TerraformPlanParseIssue(
                        message="Terraform resource change must be an object."
                    )
                )
                continue

            address = resource_change.get("address")

            if not isinstance(address, str) or not address.strip():
                issues.append(
                    TerraformPlanParseIssue(
                        message="Terraform resource change is missing a valid address."
                    )
                )
                continue

            resource_type = resource_change.get("type")

            if resource_type not in self.SUPPORTED_RESOURCE_TYPES:
                unsupported_resources.append(address)
                continue

            change = resource_change.get("change")

            if not isinstance(change, Mapping):
                issues.append(
                    TerraformPlanParseIssue(
                        resource_address=address,
                        message="Terraform resource change is missing a valid 'change' object.",
                    )
                )
                continue

            actions = change.get("actions")

            action = self._parse_action(
                actions,
                resource_address=address,
                issues=issues,
            )

            if action is None:
                continue

            changes.append(
                TerraformResourceChange(
                    resource_type=self.SUPPORTED_RESOURCE_TYPES[resource_type],
                    resource_id=address,
                    action=action,
                    region=self._extract_region(change),
                    current_quantity=self._quantity(
                        change.get("before")
                    ),
                    proposed_quantity=self._quantity(
                        change.get("after")
                    ),
                )
            )

        return TerraformPlanParseResult(
            changes=changes,
            issues=issues,
            unsupported_resources=unsupported_resources,
            resource_count=len(resource_changes),
        )

    @staticmethod
    def _parse_action(
        actions: Any,
        *,
        resource_address: str,
        issues: list[TerraformPlanParseIssue],
    ) -> TerraformChangeAction | None:
        if not isinstance(actions, list) or not actions:
            issues.append(
                TerraformPlanParseIssue(
                    resource_address=resource_address,
                    message="Terraform change is missing a valid actions list.",
                )
            )
            return None

        normalized = tuple(
            action
            for action in actions
            if isinstance(action, str)
        )

        if normalized == ("create",):
            return TerraformChangeAction.CREATE

        if normalized == ("update",):
            return TerraformChangeAction.UPDATE

        if normalized == ("delete",):
            return TerraformChangeAction.DELETE

        if normalized == ("no-op",):
            return TerraformChangeAction.NOOP

        if normalized == ("delete", "create"):
            issues.append(
                TerraformPlanParseIssue(
                    resource_address=resource_address,
                    message=(
                        "Terraform replacement action 'delete/create' is not "
                        "supported by the current cost model."
                    ),
                )
            )
            return None

        if normalized == ("create", "delete"):
            issues.append(
                TerraformPlanParseIssue(
                    resource_address=resource_address,
                    message=(
                        "Terraform replacement action 'create/delete' is not "
                        "supported by the current cost model."
                    ),
                )
            )
            return None

        issues.append(
            TerraformPlanParseIssue(
                resource_address=resource_address,
                message=f"Unsupported Terraform actions: {list(normalized)}.",
            )
        )
        return None

    @staticmethod
    def _extract_region(change: Mapping[str, Any]) -> str:
        after = change.get("after")

        if isinstance(after, Mapping):
            for key in ("region", "aws_region"):
                value = after.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        before = change.get("before")

        if isinstance(before, Mapping):
            for key in ("region", "aws_region"):
                value = before.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return "unknown"

    @staticmethod
    def _quantity(value: Any) -> float:
        """
        Extract a deterministic quantity from Terraform values.

        Terraform plans do not have a universal quantity field. The parser
        therefore uses conservative resource-value conventions and falls
        back to 1 for an existing resource representation.
        """
        if value is None:
            return 0.0

        if isinstance(value, bool):
            return 1.0 if value else 0.0

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, Mapping):
            for key in (
                "quantity",
                "count",
                "size",
                "volume_size",
                "desired_size",
                "node_count",
            ):
                candidate = value.get(key)

                if isinstance(candidate, bool):
                    continue

                if isinstance(candidate, (int, float)):
                    return float(candidate)

            return 1.0

        if isinstance(value, list):
            return float(len(value))

        return 1.0
