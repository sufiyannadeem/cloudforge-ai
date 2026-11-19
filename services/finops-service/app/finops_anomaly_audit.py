from __future__ import annotations

import os
from uuid import uuid4

import psycopg
from botocore.exceptions import BotoCoreError
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .access_control import require_finops_access
from .aws_finops_client import AWSFinOpsError
from .aws_finops_service import AWSFinOpsService
from .service_identity import frontend_identity


router = APIRouter(prefix="/api/v1/finops/aws/anomalies/captures", dependencies=[Depends(require_finops_access)])


@router.get("")
@router.post("", status_code=201)
def anomaly_captures(request: Request):
    dsn = os.getenv("FINOPS_AUDIT_DATABASE_URL")
    if not dsn:
        raise HTTPException(503, "Cost audit storage is unavailable")
    try:
        service = AWSFinOpsService()
        account = service.client.get_account_id()
        if request.method == "POST":
            subject = frontend_identity(request, "finops")["sub"]
            start, end = service.default_cost_intelligence_range(30)
            report = service.get_cost_anomalies(start_date=start, end_date=end).model_dump(mode="json")
        with psycopg.connect(dsn, connect_timeout=3, row_factory=dict_row) as db:
            db.execute("SET LOCAL statement_timeout = '3s'")
            if request.method == "POST":
                return db.execute("""
                    INSERT INTO finops_anomaly_captures (id, account_id, actor, evidence)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, actor, captured_at, evidence
                """, (uuid4(), account, subject, Jsonb(report))).fetchone()
            return db.execute("""
                SELECT id, actor, captured_at, evidence FROM finops_anomaly_captures
                WHERE account_id = %s ORDER BY captured_at DESC, id DESC LIMIT 10
            """, (account,)).fetchall()
    except (AWSFinOpsError, BotoCoreError, psycopg.Error):
        raise HTTPException(503, "AWS cost audit evidence is unavailable") from None
