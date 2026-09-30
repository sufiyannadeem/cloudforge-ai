from __future__ import annotations

import pytest

from app.terraform_cost_models import TerraformChangeAction
from app.terraform_plan_parser import TerraformPlanParser


def plan_for(
    resource_type: str,
    before,
    after,
    actions=("create",),
):
    return {
        "resource_changes": [
            {
                "address": f"{resource_type}.demo",
                "type": resource_type,
                "change": {
                    "actions": list(actions),
                    "before": before,
                    "after": after,
                },
            }
        ]
    }


@pytest.fixture
def parser() -> TerraformPlanParser:
    return TerraformPlanParser()


@pytest.mark.parametrize(
    ("resource_type", "attributes", "expected"),
    [
        (
            "aws_instance",
            {
                "region": "eu-west-1",
                "instance_type": "m7i-flex.large",
            },
            1.0,
        ),
        (
            "aws_ebs_volume",
            {
                "region": "eu-west-1",
                "volume_size": 100,
            },
            100.0,
        ),
        (
            "aws_nat_gateway",
            {
                "region": "eu-west-1",
                "allocation_id": "eipalloc",
            },
            1.0,
        ),
        (
            "aws_db_instance",
            {
                "region": "eu-west-1",
                "allocated_storage": 200,
            },
            1.0,
        ),
        (
            "aws_lb",
            {
                "region": "eu-west-1",
                "load_balancer_type": "application",
            },
            1.0,
        ),
        (
            "aws_s3_bucket",
            {
                "region": "eu-west-1",
                "lifecycle_rule": [1, 2],
            },
            1.0,
        ),
    ],
)
def test_resource_specific_quantity(
    parser: TerraformPlanParser,
    resource_type: str,
    attributes: dict,
    expected: float,
):
    result = parser.parse(
        plan_for(
            resource_type,
            None,
            attributes,
        )
    )

    assert len(result.changes) == 1
    assert result.changes[0].proposed_quantity == expected


@pytest.mark.parametrize(
    ("desired_size", "expected"),
    [
        (1, 1.0),
        (3, 3.0),
        (10, 10.0),
        (0, 0.0),
    ],
)
def test_eks_node_group_uses_desired_size(
    parser: TerraformPlanParser,
    desired_size: int,
    expected: float,
):
    result = parser.parse(
        plan_for(
            "aws_eks_node_group",
            None,
            {
                "region": "eu-west-1",
                "desired_size": desired_size,
                "min_size": 1,
                "max_size": 10,
            },
        )
    )

    assert len(result.changes) == 1
    assert result.changes[0].proposed_quantity == expected


def test_eks_node_group_without_desired_size_defaults_to_one(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_eks_node_group",
            None,
            {
                "region": "eu-west-1",
                "min_size": 1,
                "max_size": 5,
            },
        )
    )

    assert result.changes[0].proposed_quantity == 1.0


def test_update_uses_current_and_proposed_quantities(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_ebs_volume",
            {
                "region": "eu-west-1",
                "volume_size": 100,
            },
            {
                "region": "eu-west-1",
                "volume_size": 200,
            },
            actions=("update",),
        )
    )

    change = result.changes[0]

    assert change.action == TerraformChangeAction.UPDATE
    assert change.current_quantity == 100.0
    assert change.proposed_quantity == 200.0


def test_ec2_unrelated_numeric_attributes_do_not_change_quantity(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_instance",
            None,
            {
                "region": "eu-west-1",
                "instance_type": "m7i-flex.large",
                "root_block_device": [
                    {
                        "volume_size": 500,
                    }
                ],
                "monitoring": True,
            },
        )
    )

    assert result.changes[0].proposed_quantity == 1.0


def test_ebs_volume_size_is_billable_quantity(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_ebs_volume",
            None,
            {
                "region": "eu-west-1",
                "volume_size": 500,
            },
        )
    )

    assert result.changes[0].proposed_quantity == 500.0


def test_ebs_size_alias_is_supported(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_ebs_volume",
            None,
            {
                "region": "eu-west-1",
                "size": 250,
            },
        )
    )

    assert result.changes[0].proposed_quantity == 250.0


def test_rds_storage_is_not_instance_quantity(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_db_instance",
            None,
            {
                "region": "eu-west-1",
                "allocated_storage": 1000,
            },
        )
    )

    assert result.changes[0].proposed_quantity == 1.0


def test_multiple_resource_addresses_are_counted_independently(
    parser: TerraformPlanParser,
):
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web[0]",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "region": "eu-west-1",
                        "instance_type": "m7i-flex.large",
                    },
                },
            },
            {
                "address": "aws_instance.web[1]",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "region": "eu-west-1",
                        "instance_type": "m7i-flex.large",
                    },
                },
            },
        ],
    }

    result = parser.parse(plan)

    assert len(result.changes) == 2
    assert sum(
        change.proposed_quantity
        for change in result.changes
    ) == 2.0


def test_delete_uses_current_resource_quantity(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_ebs_volume",
            {
                "region": "eu-west-1",
                "volume_size": 100,
            },
            None,
            actions=("delete",),
        )
    )

    change = result.changes[0]

    assert change.action == TerraformChangeAction.DELETE
    assert change.current_quantity == 100.0
    assert change.proposed_quantity == 0.0


def test_parser_result_keeps_resource_count_compatibility(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        plan_for(
            "aws_instance",
            None,
            {"region": "eu-west-1"},
        )
    )

    assert result.resource_count == 1


def test_parse_issue_keeps_resource_address_contract(
    parser: TerraformPlanParser,
):
    result = parser.parse(
        {
            "resource_changes": [
                {
                    "address": "aws_instance.broken",
                    "type": "aws_instance",
                    "change": {
                        "actions": ["delete", "create"],
                        "before": {"region": "eu-west-1"},
                        "after": {"region": "eu-west-1"},
                    },
                }
            ]
        }
    )

    assert len(result.issues) == 1
    assert result.issues[0].resource_address == "aws_instance.broken"
    assert result.issues[0].address == "aws_instance.broken"
