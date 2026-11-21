from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .terraform_cost_models import (
    TerraformChangeAction,
    TerraformResourceChange,
    TerraformResourceType,
)


SUPPORTED_RESOURCE_TYPES = {
    resource_type.value for resource_type in TerraformResourceType
}


@dataclass(frozen=True)
class TerraformPlanParseIssue:
    resource_address: str | None
    message: str

    @property
    def address(self) -> str | None:
        """Backward-compatible alias."""
        return self.resource_address


@dataclass(frozen=True)
class TerraformPlanParseResult:
    changes: list[TerraformResourceChange]
    issues: list[TerraformPlanParseIssue]
    unsupported_resources: list[str]

    @property
    def resource_count(self) -> int:
        """Number of successfully parsed supported resources."""
        return len(self.changes)


class TerraformPlanParser:
    """
    Normalize terraform show -json resource_changes into the domain model.

    This parser never executes Terraform, calls AWS, queries pricing APIs,
    or mutates infrastructure.
    """

    def parse(self, plan: dict[str, Any]) -> TerraformPlanParseResult:
        issues: list[TerraformPlanParseIssue] = []
        changes: list[TerraformResourceChange] = []
        unsupported_resources: list[str] = []

        resource_changes = plan.get("resource_changes")

        if not isinstance(resource_changes, list):
            issues.append(
                TerraformPlanParseIssue(
                    resource_address=None,
                    message="resource_changes must be a list",
                )
            )
            return TerraformPlanParseResult(
                changes=changes,
                issues=issues,
                unsupported_resources=unsupported_resources,
            )

        for index, resource_change in enumerate(resource_changes):
            if not isinstance(resource_change, dict):
                issues.append(
                    TerraformPlanParseIssue(
                        resource_address=None,
                        message=f"resource_changes[{index}] must be an object",
                    )
                )
                continue

            address = resource_change.get("address")
            resource_type = resource_change.get("type")
            change = resource_change.get("change")

            if not isinstance(address, str) or not address.strip():
                issues.append(
                    TerraformPlanParseIssue(
                        resource_address=None,
                        message=f"resource_changes[{index}] has no valid address",
                    )
                )
                continue

            address = address.strip()

            if not isinstance(resource_type, str) or not resource_type.strip():
                issues.append(
                    TerraformPlanParseIssue(
                        resource_address=address,
                        message="resource type is missing",
                    )
                )
                continue

            resource_type = resource_type.strip()

            if resource_type not in SUPPORTED_RESOURCE_TYPES:
                unsupported_resources.append(address)
                continue

            if not isinstance(change, dict):
                issues.append(
                    TerraformPlanParseIssue(
                        resource_address=address,
                        message="change must be an object",
                    )
                )
                continue

            actions = change.get("actions")
            action = self._parse_action(address, actions, issues)

            if action is None:
                continue

            before = change.get("before")
            after = change.get("after")

            region = self._extract_region(before, after)

            current_quantity = self._extract_quantity(
                resource_type,
                before,
            )
            proposed_quantity = self._extract_quantity(
                resource_type,
                after,
            )

            changes.append(
                TerraformResourceChange(
                    resource_type=TerraformResourceType(resource_type),
                    resource_id=address,
                    action=action,
                    region=region,
                    current_quantity=current_quantity,
                    proposed_quantity=proposed_quantity,
                )
            )

        return TerraformPlanParseResult(
            changes=changes,
            issues=issues,
            unsupported_resources=unsupported_resources,
        )

    def _parse_action(
        self,
        address: str,
        actions: Any,
        issues: list[TerraformPlanParseIssue],
    ) -> TerraformChangeAction | None:
        if not isinstance(actions, list) or not actions:
            issues.append(
                TerraformPlanParseIssue(
                    resource_address=address,
                    message="change.actions must be a non-empty list",
                )
            )
            return None

        normalized = [str(action).strip().lower() for action in actions]

        if normalized == ["create"]:
            return TerraformChangeAction.CREATE

        if normalized == ["update"]:
            return TerraformChangeAction.UPDATE

        if normalized == ["delete"]:
            return TerraformChangeAction.DELETE

        if normalized == ["no-op"]:
            return TerraformChangeAction.NOOP

        if set(normalized) == {"create", "delete"}:
            issues.append(
                TerraformPlanParseIssue(
                    resource_address=address,
                    message=(
                        "replacement actions ['create', 'delete'] are not "
                        "supported by the deterministic parser"
                    ),
                )
            )
            return None

        issues.append(
            TerraformPlanParseIssue(
                resource_address=address,
                message=f"unsupported change actions: {normalized}",
            )
        )
        return None

    @staticmethod
    def _extract_region(before: Any, after: Any) -> str:
        for attributes in (after, before):
            if not isinstance(attributes, dict):
                continue

            for key in ("region", "aws_region"):
                value = attributes.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return "unknown"

    def _extract_quantity(
        self,
        resource_type: str,
        attributes: Any,
    ) -> float:
        """
        Extract the billable quantity relevant to the resource/pricing unit.

        This is intentionally resource-specific. A Terraform attribute is
        only treated as quantity when it represents a meaningful billing
        dimension for the supported resource.

        Resource-count resources:
          - aws_instance
          - aws_nat_gateway
          - aws_db_instance
          - aws_lb
          - aws_s3_bucket

        Capacity/count resources:
          - aws_ebs_volume -> volume size
          - aws_eks_node_group -> desired node count
        """
        if not isinstance(attributes, dict):
            return 0.0

        if resource_type == TerraformResourceType.AWS_INSTANCE.value:
            return 1.0

        if resource_type == TerraformResourceType.AWS_EBS_VOLUME.value:
            return self._numeric_attribute(
                attributes,
                "volume_size",
                "size",
                default=1.0,
            )

        if resource_type == TerraformResourceType.AWS_NAT_GATEWAY.value:
            return 1.0

        if resource_type == TerraformResourceType.AWS_DB_INSTANCE.value:
            return 1.0

        if resource_type == TerraformResourceType.AWS_LB.value:
            return 1.0

        if resource_type == TerraformResourceType.AWS_S3_BUCKET.value:
            return 1.0

        if resource_type == TerraformResourceType.AWS_EKS_NODE_GROUP.value:
            return self._numeric_attribute(
                attributes,
                "desired_size",
                default=1.0,
            )

        return 0.0

    @staticmethod
    def _numeric_attribute(
        attributes: dict[str, Any],
        *keys: str,
        default: float,
    ) -> float:
        for key in keys:
            value = attributes.get(key)

            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):
                return max(0.0, float(value))

        return default
