from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from . import project_costs as costs

ACCOUNT = "123456789012"
INSTANCE = "i-0123456789abcdef0"
PROJECT = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def attribution():
    return {
        "resource_id": "22222222-2222-4222-8222-222222222222",
        "project_id": PROJECT,
        "environment": "staging",
        "account_id": ACCOUNT,
        "instance_id": INSTANCE,
        "region": "us-east-1",
        "verified_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


def ec2_response(row, owner=ACCOUNT, tags=None):
    return {"Reservations": [{"OwnerId": owner, "Instances": [{
        "InstanceId": row["instance_id"], "State": {"Name": "running"},
        "Tags": [{"Key": key, "Value": value} for key, value in (tags or costs.expected_tags(row)).items()],
    }]}]}


def test_invalid_tag_and_account_are_unattributed(attribution):
    requested = {INSTANCE: attribution}
    for key in costs.expected_tags(attribution):
        tags = {**costs.expected_tags(attribution), key: "forged"}
        assert not costs.verified_instances(ec2_response(attribution, tags=tags), ACCOUNT, requested)
    assert not costs.verified_instances(ec2_response(attribution, owner="000000000000"), ACCOUNT, requested)


def test_billing_is_resource_scoped_and_distinguishes_estimates(monkeypatch, attribution):
    billing = Mock()
    monkeypatch.setattr(costs, "AWSFinOpsClient", lambda **_: SimpleNamespace(
        get_account_id=lambda: ACCOUNT, cost_explorer=billing,
    ))
    ec2 = Mock()
    ec2.describe_instances.return_value = ec2_response(attribution)
    monkeypatch.setattr(costs.boto3, "client", lambda *_args, **_kwargs: ec2)

    def day(start, estimated, instance=INSTANCE):
        return {"TimePeriod": {"Start": start}, "Estimated": estimated, "Groups": [{
            "Keys": [instance], "Metrics": {"UnblendedCost": {"Amount": "2.50", "Unit": "USD"}},
        }]}

    billing.get_cost_and_usage_with_resources.return_value = {
        "ResultsByTime": [day("2026-01-02T00:00:00Z", False), day("2026-01-03", True)],
    }
    totals, covered = costs.costs_for_region([attribution], date(2026, 1, 4))
    assert covered == {INSTANCE}
    assert {row["status"]: row["amount"] for row in totals} == {"actual": "2.50", "estimated": "2.50"}
    filters = billing.get_cost_and_usage_with_resources.call_args.kwargs["Filter"]["And"]
    assert {x["Dimensions"]["Key"]: x["Dimensions"]["Values"] for x in filters} == {
        "SERVICE": [costs.EC2_SERVICE], "LINKED_ACCOUNT": [ACCOUNT], "REGION": ["us-east-1"], "RESOURCE_ID": [INSTANCE],
    }
    billing.get_cost_and_usage_with_resources.return_value["ResultsByTime"].append(
        day("2026-01-03", False, "i-11111111"),
    )
    with pytest.raises(ValueError, match="unexpected billing attribution"):
        costs.costs_for_region([attribution], date(2026, 1, 4))


def test_project_membership_denial_precedes_attribution(monkeypatch):
    db = Mock()
    db.execute.return_value.fetchone.return_value = None
    connection = Mock()
    connection.__enter__ = Mock(return_value=db)
    connection.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(costs.psycopg, "connect", lambda *_args, **_kwargs: connection)
    with pytest.raises(HTTPException) as denied:
        costs.project_resources("trusted-dsn", PROJECT, {"role": "developer", "sub": "other-user"})
    assert denied.value.status_code == 404
    assert db.execute.call_count == 2
    assert db.execute.call_args.args[1] == (PROJECT, False, "other-user", "other-user")


def test_cost_route_rejects_untrusted_identity_and_resource_selectors(monkeypatch):
    def request(query=b""):
        return Request({"type": "http", "method": "GET", "path": "/", "query_string": query, "headers": [
            (b"x-cloudforge-role", b"platform-engineer"),
        ]})

    with pytest.raises(HTTPException) as missing:
        costs.project_costs(PROJECT, request(), Response())
    assert missing.value.status_code in {401, 503}
    monkeypatch.setattr(costs, "frontend_identity", lambda *_: {"role": "developer", "sub": "alice"})
    with pytest.raises(HTTPException) as selector:
        costs.project_costs(PROJECT, request(b"resource_id=i-11111111"), Response())
    assert selector.value.status_code == 400
    assert costs.router.routes[0].methods == {"GET"}


def test_incident_resource_costs_reject_unrelated_resource(monkeypatch, attribution):
    from uuid import UUID

    monkeypatch.setenv("FINOPS_PROJECT_DATABASE_URL", "test-only")
    monkeypatch.setattr(costs, "frontend_identity", lambda *_: {"role": "sre", "sub": "operator"})
    monkeypatch.setattr(costs, "project_resources", lambda *_: [attribution])
    request = Request({"type": "http", "query_string": b""})
    with pytest.raises(HTTPException) as exc:
        costs.project_costs(UUID(PROJECT), request, Response(), UUID("33333333-3333-4333-8333-333333333333"))
    assert exc.value.status_code == 404


def test_incident_resource_costs_query_only_attributed_instance(monkeypatch, attribution):
    from uuid import UUID

    other = {**attribution, "resource_id": "33333333-3333-4333-8333-333333333333", "instance_id": "i-11111111111111111"}
    monkeypatch.setenv("FINOPS_PROJECT_DATABASE_URL", "test-only")
    monkeypatch.setattr(costs, "frontend_identity", lambda *_: {"role": "sre", "sub": "operator"})
    monkeypatch.setattr(costs, "project_resources", lambda *_: [attribution, other])
    def measured(rows, _today):
        assert len(rows) == 1 and rows[0]["instance_id"] == INSTANCE
        return [{"status": "actual", "currency": "USD", "amount": "1.00"}], {INSTANCE}
    monkeypatch.setattr(costs, "costs_for_region", measured)
    request = Request({"type": "http", "query_string": b""})
    result = costs.project_costs(UUID(PROJECT), request, Response(), UUID(attribution["resource_id"]))
    assert result["status"] == "available"
    assert result["resources_with_cost"] == 1
