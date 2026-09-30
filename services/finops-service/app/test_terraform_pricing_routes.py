from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def pricing_payload(
    *,
    resource_type: str = "aws_instance",
    region: str = "eu-west-1",
    unit: str = "instance-month",
    price: float = 25.0,
) -> dict:
    return {
        "resource_type": resource_type,
        "region": region,
        "unit": unit,
        "unit_monthly_usd": price,
        "source": "approved-test-evidence",
        "evidence_available": True,
        "confidence": "high",
        "assumptions": [
            "Explicit test pricing evidence."
        ],
    }


def auth_headers() -> dict[str, str]:
    return {
        "X-CloudForge-Role": "platform-engineer",
    }


def test_pricing_requires_finops_access() -> None:
    response = client.get(
        "/api/v1/terraform/pricing",
    )

    assert response.status_code == 403


def test_create_pricing_rate_card() -> None:
    response = client.post(
        "/api/v1/terraform/pricing",
        headers=auth_headers(),
        json=pricing_payload(),
    )

    assert response.status_code == 201

    body = response.json()

    assert body["resource_type"] == "aws_instance"
    assert body["region"] == "eu-west-1"
    assert body["unit"] == "instance-month"
    assert body["unit_monthly_usd"] == 25.0
    assert body["source"] == "approved-test-evidence"
    assert body["evidence_available"] is True


def test_duplicate_pricing_returns_conflict() -> None:
    payload = pricing_payload(
        resource_type="aws_nat_gateway",
        unit="gateway-month",
    )

    first = client.post(
        "/api/v1/terraform/pricing",
        headers=auth_headers(),
        json=payload,
    )

    second = client.post(
        "/api/v1/terraform/pricing",
        headers=auth_headers(),
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_list_pricing_rate_cards() -> None:
    response = client.get(
        "/api/v1/terraform/pricing",
        headers=auth_headers(),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["count"] >= 1
    assert isinstance(body["records"], list)
    assert body["generated_by"] == "cloudforge-finops-pricing-v1"


def test_list_can_filter_by_resource_type() -> None:
    response = client.get(
        "/api/v1/terraform/pricing",
        params={"resource_type": "aws_nat_gateway"},
        headers=auth_headers(),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["count"] >= 1

    for record in body["records"]:
        assert record["resource_type"] == "aws_nat_gateway"


def test_get_pricing_rate_card() -> None:
    response = client.get(
        "/api/v1/terraform/pricing/aws_nat_gateway/eu-west-1/gateway-month",
        headers=auth_headers(),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["resource_type"] == "aws_nat_gateway"
    assert body["region"] == "eu-west-1"
    assert body["unit"] == "gateway-month"


def test_missing_pricing_returns_not_found() -> None:
    response = client.get(
        "/api/v1/terraform/pricing/aws_instance/eu-west-1/nonexistent-unit",
        headers=auth_headers(),
    )

    assert response.status_code == 404


def test_invalid_price_is_rejected() -> None:
    payload = pricing_payload(
        resource_type="aws_s3_bucket",
        unit="bucket-month",
        price=-1.0,
    )

    response = client.post(
        "/api/v1/terraform/pricing",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422


def test_invalid_confidence_is_rejected() -> None:
    payload = pricing_payload(
        resource_type="aws_ebs_volume",
        unit="gb-month",
    )
    payload["confidence"] = "certain"

    response = client.post(
        "/api/v1/terraform/pricing",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
