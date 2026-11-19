from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

import boto3
import psycopg
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg.rows import dict_row

from .aws_finops_client import AWSFinOpsClient, AWSFinOpsError
from .service_identity import frontend_identity

router = APIRouter(prefix="/api/v1/finops/projects", tags=["Project FinOps"])
AWS_LIMITS = Config(connect_timeout=2, read_timeout=4, retries={"total_max_attempts": 1})
INSTANCE = re.compile(r"i-(?:[0-9a-f]{8}|[0-9a-f]{17})")
REGION = re.compile(r"[a-z]{2}(?:-[a-z]+)+-[0-9]+")
ACCOUNT = re.compile(r"[0-9]{12}")
EC2_SERVICE = "Amazon Elastic Compute Cloud - Compute"


def project_resources(dsn: str, project: UUID, claims: dict) -> list[dict]:
    with psycopg.connect(dsn, connect_timeout=3, options="-c statement_timeout=3000", row_factory=dict_row) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        allowed = db.execute("""
            SELECT 1 FROM projects p
            WHERE p.id = %s AND (%s OR (p.created_by IS NOT NULL AND (
                p.created_by = %s OR EXISTS (
                    SELECT 1 FROM project_members m WHERE m.project_id = p.id AND m.username = %s
                )
            )))
        """, (project, claims["role"] != "developer", claims["sub"], claims["sub"])).fetchone()
        if not allowed:
            raise HTTPException(404, "Project not found")
        return db.execute("""
            SELECT r.id AS resource_id, r.project_id, r.environment, r.region,
                   a.account_id, a.instance_id, a.verified_at
            FROM infrastructure_resources r
            LEFT JOIN infrastructure_ec2_attribution a ON a.resource_id = r.id
              AND a.project_id = r.project_id AND a.environment = r.environment AND a.region = r.region
            WHERE r.project_id = %s AND r.status = 'active' AND r.provider = 'aws'
              AND r.resource_type = 'aws_ec2'
            ORDER BY r.id LIMIT 21
        """, (project,)).fetchall()


def expected_tags(row: dict) -> dict[str, str]:
    return {
        "cloudforge:resource-id": str(row["resource_id"]),
        "cloudforge:project-id": str(row["project_id"]),
        "cloudforge:environment": row["environment"],
    }


def verified_instances(response: dict, account: str, requested: dict[str, dict]) -> set[str]:
    checked = set()
    for reservation in response.get("Reservations", []):
        if reservation.get("OwnerId") != account:
            continue
        for instance in reservation.get("Instances", []):
            instance_id = instance.get("InstanceId")
            row = requested.get(instance_id)
            if row is None or instance.get("State", {}).get("Name") not in {"pending", "running", "stopping", "stopped"}:
                continue
            tags = instance.get("Tags", [])
            for key, value in expected_tags(row).items():
                if [tag.get("Value") for tag in tags if tag.get("Key") == key] != [value]:
                    break
            else:
                checked.add(instance_id)
    return checked


def costs_for_region(rows: list[dict], today: date) -> tuple[list[dict], set[str]]:
    region, account = rows[0]["region"], rows[0]["account_id"]
    client = AWSFinOpsClient(region=region, client_config=AWS_LIMITS)
    if client.get_account_id() != account:
        return [], set()
    requested = {row["instance_id"]: row for row in rows}
    ec2 = boto3.client("ec2", region_name=region, config=AWS_LIMITS)
    result = ec2.describe_instances(InstanceIds=sorted(requested))
    verified = verified_instances(result, account, requested)
    start_by_id = {
        instance: max(today - timedelta(days=7), requested[instance]["verified_at"].astimezone(UTC).date() + timedelta(days=1))
        for instance in verified
    }
    eligible = {key: value for key, value in start_by_id.items() if value < today}
    if not eligible:
        return [], set()
    params = {
        "TimePeriod": {"Start": min(eligible.values()).isoformat(), "End": today.isoformat()},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "RESOURCE_ID"}],
        "Filter": {"And": [
            {"Dimensions": {"Key": key, "Values": values}}
            for key, values in (
                ("SERVICE", [EC2_SERVICE]), ("LINKED_ACCOUNT", [account]),
                ("REGION", [region]), ("RESOURCE_ID", sorted(eligible)),
            )
        ]},
    }
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    covered: set[str] = set()
    seen: set[tuple[str, date]] = set()
    for _ in range(4):
        page = client.cost_explorer.get_cost_and_usage_with_resources(**params)
        for day in page["ResultsByTime"]:
            period = date.fromisoformat(day["TimePeriod"]["Start"][:10])
            if type(day.get("Estimated")) is not bool:
                raise ValueError("unverified cost quality")
            quality = "estimated" if day["Estimated"] else "actual"
            for group in day.get("Groups", []):
                keys = group["Keys"]
                if len(keys) != 1 or keys[0] not in eligible or period >= today:
                    raise ValueError("unexpected billing attribution")
                instance = keys[0]
                if (instance, period) in seen:
                    raise ValueError("duplicate resource billing row")
                seen.add((instance, period))
                if period < eligible[instance]:
                    continue
                cost = group["Metrics"]["UnblendedCost"]
                value, currency = Decimal(cost["Amount"]), cost["Unit"]
                if not value.is_finite() or not re.fullmatch(r"[A-Z]{3}", currency):
                    raise ValueError("invalid cost data")
                totals[(quality, currency)] += value
                covered.add(instance)
        token = page.get("NextPageToken")
        if not token:
            return [
                {"status": quality, "currency": currency, "amount": str(value)}
                for (quality, currency), value in sorted(totals.items())
            ], covered
        params["NextPageToken"] = token
    return [], set()


@router.get("/{project_id}/resources/{resource_id}/costs")
@router.get("/{project_id}/costs")
def project_costs(project_id: UUID, request: Request, response: Response, resource_id: UUID | None = None) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    claims = frontend_identity(request, "finops")
    if request.query_params:
        raise HTTPException(400, "Cost selectors are managed by the service")
    dsn = os.getenv("FINOPS_PROJECT_DATABASE_URL")
    if not dsn:
        raise HTTPException(503, "Project attribution database unavailable")
    try:
        rows = project_resources(dsn, project_id, claims)
    except psycopg.Error:
        raise HTTPException(503, "Project attribution unavailable") from None

    if resource_id is not None:
        rows = [row for row in rows if str(row["resource_id"]) == str(resource_id)]
        if not rows:
            raise HTTPException(404, "Resource attribution unavailable")
    unavailable = {"project_id": str(project_id), "status": "unavailable", "costs": [],
                   "resources_with_cost": 0, "active_ec2_resources": len(rows)}
    if len(rows) > 20:
        return {**unavailable, "active_ec2_resources": None}
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if (row["verified_at"] and INSTANCE.fullmatch(row["instance_id"] or "")
                and ACCOUNT.fullmatch(row["account_id"] or "") and REGION.fullmatch(row["region"])):
            grouped[(row["account_id"], row["region"])].append(row)
    if not grouped or len(grouped) > 4:
        return unavailable

    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    with_cost = 0
    for group in grouped.values():
        try:
            amounts, covered = costs_for_region(group, datetime.now(UTC).date())
            with_cost += len(covered)
            for item in amounts:
                totals[(item["status"], item["currency"])] += Decimal(item["amount"])
        except (AWSFinOpsError, ClientError, BotoCoreError, ValueError, TypeError, KeyError, InvalidOperation):
            continue
    return {**unavailable, "status": "available" if totals else "unavailable",
            "resources_with_cost": with_cost,
            "costs": [{"status": kind, "currency": currency, "amount": str(value)}
                      for (kind, currency), value in sorted(totals.items())]}
