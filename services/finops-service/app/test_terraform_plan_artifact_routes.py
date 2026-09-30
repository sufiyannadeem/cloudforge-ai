from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def create_plan() -> dict:
    return {
        "format_version": "1.0",
        "resource_changes": [
            {
                "address": "aws_instance.demo",
                "mode": "managed",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "region": "eu-west-1",
                        "instance_type": "m7i-flex.large",
                    },
                },
            }
        ],
    }


def test_plan_artifact_endpoint_requires_role() -> None:
    response = client.post(
        "/api/v1/terraform/plan-artifact-cost-estimate",
        json={
            "source": "github-actions",
            "workspace": "cloudforge",
            "environment": "production",
            "region": "eu-west-1",
            "plan": create_plan(),
        },
    )

    assert response.status_code == 403


def test_plan_artifact_endpoint_returns_artifact_and_coverage() -> None:
    response = client.post(
        "/api/v1/terraform/plan-artifact-cost-estimate",
        headers={
            "X-CloudForge-Role": "platform-engineer",
        },
        json={
            "source": "github-actions",
            "workspace": "cloudforge",
            "environment": "production",
            "region": "eu-west-1",
            "artifact_id": "plan-test-001",
            "plan": create_plan(),
            "pricing": {
                "aws_instance.demo": {
                    "unit_monthly_usd": 25.0,
                    "source": "approved-pricing-evidence",
                    "evidence_available": True,
                    "confidence": "high",
                    "assumptions": [
                        "Monthly unit price supplied externally"
                    ],
                }
            },
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["artifact"]["artifact_id"] == "plan-test-001"
    assert payload["artifact"]["source"] == "github-actions"
    assert payload["artifact"]["workspace"] == "cloudforge"
    assert payload["artifact"]["environment"] == "production"
    assert payload["artifact"]["region"] == "eu-west-1"

    assert payload["artifact"]["resource_count"] == 1
    assert len(payload["artifact"]["plan_hash"]) == 64

    assert payload["parsed_resource_count"] == 1

    assert payload["evidence_coverage"] == {
        "parsed_resource_count": 1,
        "priced_resource_count": 1,
        "missing_pricing_resource_count": 0,
        "coverage_percent": 100.0,
        "complete": True,
    }


def test_plan_artifact_endpoint_rejects_malformed_plan() -> None:
    response = client.post(
        "/api/v1/terraform/plan-artifact-cost-estimate",
        headers={
            "X-CloudForge-Role": "platform-engineer",
        },
        json={
            "source": "github-actions",
            "workspace": "cloudforge",
            "environment": "production",
            "region": "eu-west-1",
            "plan": {
                "resource_changes": "invalid"
            },
        },
    )

    assert response.status_code == 422
