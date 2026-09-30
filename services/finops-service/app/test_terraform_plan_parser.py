import sys
from pathlib import Path

FINOPS_SERVICE_DIR = Path(__file__).resolve().parent.parent

if str(FINOPS_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(FINOPS_SERVICE_DIR))

from app.terraform_cost_models import TerraformChangeAction  # noqa: E402
from app.terraform_plan_parser import TerraformPlanParser  # noqa: E402


def test_parse_create_resource():
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "mode": "managed",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "region": "eu-west-1",
                    },
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert result.resource_count == 1
    assert result.issues == []
    assert result.unsupported_resources == []
    assert len(result.changes) == 1

    change = result.changes[0]

    assert change.resource_id == "aws_instance.web"
    assert change.action is TerraformChangeAction.CREATE
    assert change.region == "eu-west-1"
    assert change.current_quantity == 0
    assert change.proposed_quantity == 1


def test_parse_update_resource_with_quantities():
    plan = {
        "resource_changes": [
            {
                "address": "aws_ebs_volume.data",
                "type": "aws_ebs_volume",
                "change": {
                    "actions": ["update"],
                    "before": {
                        "region": "eu-west-1",
                        "size": 100,
                    },
                    "after": {
                        "region": "eu-west-1",
                        "size": 150,
                    },
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert len(result.changes) == 1

    change = result.changes[0]

    assert change.action is TerraformChangeAction.UPDATE
    assert change.region == "eu-west-1"
    assert change.current_quantity == 100
    assert change.proposed_quantity == 150


def test_parse_delete_resource():
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["delete"],
                    "before": {
                        "region": "eu-west-1",
                    },
                    "after": None,
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert len(result.changes) == 1

    change = result.changes[0]

    assert change.action is TerraformChangeAction.DELETE
    assert change.current_quantity == 1
    assert change.proposed_quantity == 0


def test_parse_noop_resource():
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["no-op"],
                    "before": {
                        "region": "eu-west-1",
                    },
                    "after": {
                        "region": "eu-west-1",
                    },
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert len(result.changes) == 1
    assert result.changes[0].action is TerraformChangeAction.NOOP


def test_unsupported_resource_is_reported_without_cost_inference():
    plan = {
        "resource_changes": [
            {
                "address": "aws_lambda_function.worker",
                "type": "aws_lambda_function",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {},
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert result.resource_count == 1
    assert result.changes == []
    assert result.issues == []
    assert result.unsupported_resources == ["aws_lambda_function.worker"]


def test_missing_actions_are_reported():
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "before": None,
                    "after": {},
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert result.changes == []
    assert len(result.issues) == 1
    assert result.issues[0].resource_address == "aws_instance.web"


def test_replacement_is_not_silently_mapped():
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["delete", "create"],
                    "before": {
                        "region": "eu-west-1",
                    },
                    "after": {
                        "region": "eu-west-1",
                    },
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert result.changes == []
    assert len(result.issues) == 1
    assert "replacement" in result.issues[0].message


def test_invalid_resource_changes_shape_is_reported():
    result = TerraformPlanParser().parse(
        {
            "resource_changes": {
                "aws_instance.web": {}
            }
        }
    )

    assert result.changes == []
    assert len(result.issues) == 1
    assert "must be a list" in result.issues[0].message


def test_multiple_supported_resources_are_normalized():
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"region": "eu-west-1"},
                },
            },
            {
                "address": "aws_nat_gateway.main",
                "type": "aws_nat_gateway",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"region": "eu-west-1"},
                },
            },
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert result.resource_count == 2
    assert len(result.changes) == 2
    assert result.unsupported_resources == []
    assert {change.resource_id for change in result.changes} == {
        "aws_instance.web",
        "aws_nat_gateway.main",
    }


def test_missing_region_is_explicitly_unknown():
    plan = {
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {},
                },
            }
        ]
    }

    result = TerraformPlanParser().parse(plan)

    assert len(result.changes) == 1
    assert result.changes[0].region == "unknown"


def test_empty_plan_is_valid():
    result = TerraformPlanParser().parse(
        {
            "resource_changes": []
        }
    )

    assert result.changes == []
    assert result.issues == []
    assert result.unsupported_resources == []
    assert result.resource_count == 0
