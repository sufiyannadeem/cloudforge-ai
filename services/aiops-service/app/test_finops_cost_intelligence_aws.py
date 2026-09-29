from __future__ import annotations

from unittest.mock import MagicMock

from .aws_finops_client import AWSFinOpsClient


def test_daily_cost_history():
    client = object.__new__(
        AWSFinOpsClient
    )

    mock_ce = MagicMock()

    mock_ce.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "TimePeriod": {
                    "Start": "2026-09-25",
                    "End": "2026-09-26",
                },
                "Total": {
                    "UnblendedCost": {
                        "Amount": "2.50",
                        "Unit": "USD",
                    }
                },
            },
            {
                "TimePeriod": {
                    "Start": "2026-09-26",
                    "End": "2026-09-27",
                },
                "Total": {
                    "UnblendedCost": {
                        "Amount": "3.50",
                        "Unit": "USD",
                    }
                },
            },
        ]
    }

    client.cost_explorer = mock_ce

    result = client.get_daily_cost_history(
        start_date="2026-09-25",
        end_date="2026-09-27",
    )

    assert len(result) == 2
    assert result[0]["amount"] == 2.5
    assert result[1]["amount"] == 3.5


def test_tag_costs():
    client = object.__new__(
        AWSFinOpsClient
    )

    mock_ce = MagicMock()

    mock_ce.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "Groups": [
                    {
                        "Keys": ["Environment$dev"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "2.50",
                            }
                        },
                    },
                    {
                        "Keys": ["Environment$prod"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "7.50",
                            }
                        },
                    },
                ]
            }
        ]
    }

    client.cost_explorer = mock_ce

    result = client.get_tag_costs(
        start_date="2026-09-25",
        end_date="2026-09-27",
        tag_key="Environment",
    )

    assert result[0]["value"] == "prod"
    assert result[0]["amount"] == 7.5
    assert result[1]["value"] == "dev"
    assert result[1]["amount"] == 2.5


def test_budget_read_only_call():
    client = object.__new__(
        AWSFinOpsClient
    )

    mock_budgets = MagicMock()

    mock_budgets.describe_budgets.return_value = {
        "Budgets": [
            {
                "BudgetName": "CloudForge-dev",
                "BudgetType": "COST",
                "TimeUnit": "MONTHLY",
                "BudgetLimit": {
                    "Amount": "50",
                    "Unit": "USD",
                },
                "CalculatedSpend": {
                    "ActualSpend": {
                        "Amount": "20",
                        "Unit": "USD",
                    },
                    "ForecastedSpend": {
                        "Amount": "35",
                        "Unit": "USD",
                    },
                },
            }
        ]
    }

    client.budgets = mock_budgets

    result = client.get_budgets(
        account_id="123456789012"
    )

    assert len(result) == 1
    assert result[0]["BudgetName"] == (
        "CloudForge-dev"
    )

    mock_budgets.describe_budgets.assert_called_once_with(
        AccountId="123456789012",
        MaxResults=100,
    )


if __name__ == "__main__":
    test_daily_cost_history()
    test_tag_costs()
    test_budget_read_only_call()

    print(
        "ALL FINOPS COST INTELLIGENCE AWS TESTS PASSED"
    )
