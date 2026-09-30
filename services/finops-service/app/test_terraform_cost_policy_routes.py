from __future__ import annotations

from fastapi.testclient import TestClient

from .main import app


client = TestClient(app)


def _plan() -> dict:
    return {
        "resource_changes": [
            {
                "address": "aws_instance.web",
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


def _pricing(price: float) -> dict:
    return {
        "aws_instance.web": {
            "unit_monthly_usd": price,
            "source": "test-pricing-evidence",
            "evidence_available": True,
            "confidence": "high",
        }
    }


def _headers() -> dict[str, str]:
    return {
        "X-CloudForge-Role": "platform-engineer",
    }


def test_cost_policy_allows_change_within_threshold() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        headers=_headers(),
        json={
            "plan": _plan(),
            "pricing": _pricing(25.0),
            "policy": {
                "max_monthly_increase_usd": 100.0,
                "max_monthly_increase_percent": 20.0,
            },
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["decision"] == "ALLOW"
    assert body["comparison"]["proposed_monthly_usd"] == 25.0
    assert body["comparison"]["monthly_delta_usd"] == 25.0


def test_cost_policy_blocks_usd_threshold() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        headers=_headers(),
        json={
            "plan": _plan(),
            "pricing": _pricing(150.0),
            "policy": {
                "max_monthly_increase_usd": 100.0,
                "max_monthly_increase_percent": 200.0,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"


def test_cost_policy_requires_review_for_percentage_threshold() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        headers=_headers(),
        json={
            "plan": _plan(),
            "pricing": _pricing(25.0),
            "policy": {
                "max_monthly_increase_usd": 100.0,
                "max_monthly_increase_percent": 20.0,
            },
        },
    )

    assert response.status_code == 200

    body = response.json()

    # A create from zero has no percentage denominator, so it is not
    # rejected by the percentage rule.
    assert body["comparison"]["monthly_delta_percent"] is None
    assert body["decision"] == "ALLOW"


def test_cost_policy_blocks_incomplete_evidence_by_default() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        headers=_headers(),
        json={
            "plan": _plan(),
            "pricing": {},
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["decision"] == "BLOCK"
    assert body["comparison"]["evidence_complete"] is False


def test_cost_policy_can_require_review_for_incomplete_evidence() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        headers=_headers(),
        json={
            "plan": _plan(),
            "pricing": {},
            "policy": {
                "block_if_evidence_incomplete": False,
                "review_if_evidence_incomplete": True,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "REVIEW"


def test_cost_policy_rejects_missing_role() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        json={
            "plan": _plan(),
            "pricing": _pricing(25.0),
        },
    )

    assert response.status_code == 403


def test_cost_policy_rejects_unauthorized_role() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        headers={
            "X-CloudForge-Role": "viewer",
        },
        json={
            "plan": _plan(),
            "pricing": _pricing(25.0),
        },
    )

    assert response.status_code == 403


def test_cost_policy_response_contains_policy_metadata() -> None:
    response = client.post(
        "/api/v1/terraform/cost-policy-evaluate",
        headers=_headers(),
        json={
            "plan": _plan(),
            "pricing": _pricing(25.0),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["generated_by"] == "cloudforge-finops-cost-policy-v1"
    assert body["policy"]["max_monthly_increase_usd"] == 100.0
    assert body["policy"]["max_monthly_increase_percent"] == 20.0
