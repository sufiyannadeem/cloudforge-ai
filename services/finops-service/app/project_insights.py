"""Read-only project insights. No account inventory, caller observations or actions."""
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isfinite
import os
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Request, Response
import psycopg

from . import project_costs as attribution
from .finops_cost_intelligence import detect_cost_anomalies
from .finops_optimization_engine import FinOpsOptimizationEngine
from .finops_optimization_models import AWSOptimizationObservation, EC2Observation
from .service_identity import frontend_identity

router = APIRouter(prefix='/api/v1/finops/projects', tags=['Project FinOps'])
FAILURES = (attribution.AWSFinOpsError, BotoCoreError, ClientError, ValueError, TypeError, KeyError, InvalidOperation)


def authorized_rows(project_id, request, response):
    response.headers['Cache-Control'] = 'private, no-store'
    claims = frontend_identity(request, 'finops')
    if request.query_params:
        raise HTTPException(400, 'Insight selectors are managed by the service')
    dsn = os.getenv('FINOPS_PROJECT_DATABASE_URL')
    if not dsn:
        raise HTTPException(503, 'Project attribution database unavailable')
    try:
        rows = attribution.project_resources(dsn, project_id, claims)
    except psycopg.Error:
        raise HTTPException(503, 'Project attribution unavailable') from None
    if os.getenv('CLOUDFORGE_AWS_BILLING_ENABLED', 'true').lower() == 'false':
        raise HTTPException(503, 'AWS-backed insights are disabled in this environment')
    # Enforce the same bounded attribution contract as project costs. Never return
    # a partial unbounded project or trust a foreign row from a join/cache defect.
    if len(rows) > 20 or any(str(row['project_id']) != str(project_id) for row in rows):
        raise HTTPException(503, 'Project attribution is incomplete')
    return rows


def groups_for(rows, now):
    groups = defaultdict(list)
    for row in rows:
        verified = row.get('verified_at')
        if (isinstance(verified, datetime) and verified.tzinfo and verified <= now
                and attribution.INSTANCE.fullmatch(row.get('instance_id') or '')
                and attribution.ACCOUNT.fullmatch(row.get('account_id') or '')
                and attribution.REGION.fullmatch(row.get('region') or '')):
            groups[(row['account_id'], row['region'])].append(row)
    if len(groups) > 4 or any(len({row['instance_id'] for row in group}) != len(group) for group in groups.values()):
        return {}
    return groups


def billing_by_resource(group, now, *, days):
    amounts, _ = attribution.costs_for_region(group, now.date(), window_days=days)
    allowed = {str(row['resource_id']) for row in group}
    histories = defaultdict(list)
    for item in amounts:
        for day in item.get('resource_history', []):
            if day['resource_id'] not in allowed:
                raise ValueError('Foreign billing attribution')
            histories[day['resource_id']].append({
                'date': day['date'], 'amount': day['amount'],
                'currency': item['currency'], 'status': item['status'],
            })
    return histories


def quality(history):
    return 'estimated' if any(day['status'] == 'estimated' for day in history) else 'actual' if history else 'unavailable'


@router.get('/{project_id}/anomalies')
def project_anomalies(project_id: UUID, request: Request, response: Response):
    rows = authorized_rows(project_id, request, response)
    now = datetime.now(UTC)
    evidence = {}
    for group in groups_for(rows, now).values():
        try:
            evidence.update(billing_by_resource(group, now, days=14))
        except FAILURES:
            continue
    resources = []
    for row in rows:
        resource_id = str(row['resource_id'])
        history = evidence.get(resource_id, [])
        findings = []
        available = False
        sufficient_currencies = 0
        currencies = sorted({day['currency'] for day in history})
        # Never join currencies, fill missing days with zero, or evaluate a trend
        # against a different resource's changing coverage. Eight consecutive
        # resource-attributed days provide seven baseline points plus an observation.
        for currency in currencies:
            daily = defaultdict(Decimal)
            estimated = set()
            for day in history:
                if day['currency'] == currency:
                    daily[day['date']] += Decimal(day['amount'])
                    if day['status'] == 'estimated':
                        estimated.add(day['date'])
            dates = sorted(daily)
            contiguous = len(dates) >= 8 and dates[-1] == (now.date()-timedelta(days=1)).isoformat() and all(
                datetime.fromisoformat(b) - datetime.fromisoformat(a) == timedelta(days=1)
                for a, b in zip(dates, dates[1:]))
            if not contiguous or any(not value.is_finite() for value in daily.values()):
                continue
            points = [{'date': day, 'amount': float(daily[day]), 'currency': currency,
                       'estimated': day in estimated} for day in dates]
            if not all(isfinite(point['amount']) for point in points):
                continue
            available = True
            sufficient_currencies += 1
            findings.extend({**finding.model_dump(mode='json'),
                             'evidence_quality': 'estimated' if estimated else 'actual'}
                            for finding in detect_cost_anomalies(points=points))
        resources.append({'resource_id': resource_id, 'status': ('available' if sufficient_currencies == len(currencies) else 'partial') if available else 'unavailable',
                          'billing_quality': quality(history), 'sample_count': len({d['date'] for d in history}),
                          'anomalies': findings,
                          'reason': ('Some currency series lack sufficient comparable evidence.' if sufficient_currencies < len(currencies) else None) if available else 'Eight consecutive attributed billing days are required.'})
    return {'project_id': str(project_id), 'status': coverage(resources), 'resources': resources,
            'window_days': 14, 'advisory_only': True, 'observed_at': now.isoformat()}


def coverage(resources):
    if resources and all(row['status'] == 'available' for row in resources):
        return 'available'
    return 'partial' if any(row['status'] in {'available', 'partial'} for row in resources) else 'unavailable'


@router.get('/{project_id}/optimizations')
def project_optimizations(project_id: UUID, request: Request, response: Response):
    rows = authorized_rows(project_id, request, response)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    results = {}
    for (account, region), group in groups_for(rows, now).items():
        try:
            client = attribution.AWSFinOpsClient(region=region, client_config=attribution.AWS_LIMITS)
            if client.get_account_id() != account:
                continue
            requested = {row['instance_id']: row for row in group}
            ec2 = attribution.boto3.client('ec2', region_name=region, config=attribution.AWS_LIMITS)
            snapshot = ec2.describe_instances(InstanceIds=sorted(requested))
            verified = attribution.verified_instances(snapshot, account, requested)
            instances = {instance['InstanceId']: instance for reservation in snapshot.get('Reservations', [])
                         for instance in reservation.get('Instances', []) if instance.get('InstanceId') in verified}
            try:
                billing = billing_by_resource(group, now, days=7)
            except FAILURES:
                billing = {}
            for instance_id in sorted(verified):
                row = requested[instance_id]
                resource_id = str(row['resource_id'])
                # Do not use telemetry from before this resource's verified ownership.
                if row['verified_at'] > now - timedelta(days=1):
                    continue
                try:
                    metric = client.get_ec2_cpu_utilization(instance_id=instance_id,
                        start_time=now-timedelta(days=1), end_time=now, period_seconds=3600)
                    cpu = metric.get('cpu_utilization_percent')
                    if (metric.get('instance_id') != instance_id or metric.get('utilization_available') is not True
                            or type(cpu) not in (int, float) or not isfinite(cpu) or not 0 <= cpu <= 100
                            or type(metric.get('datapoints_count')) is not int or metric['datapoints_count'] < 24):
                        continue
                    instance_type = instances[instance_id].get('InstanceType')
                    if not instance_type:
                        continue
                    observation = EC2Observation(resource_id=resource_id, instance_type=instance_type,
                        cpu_utilization_percent=cpu, utilization_available=True, period_seconds=3600,
                        datapoints_count=metric['datapoints_count'])
                    recommendations = FinOpsOptimizationEngine().analyze_aws(AWSOptimizationObservation(ec2=[observation]))
                    findings = []
                    for finding in recommendations:
                        item = finding.model_dump(mode='json')
                        # The shared engine uses zero as an unavailable sentinel.
                        # The project API exposes null; absence never means $0 savings.
                        item['potential_monthly_savings_usd'] = None
                        item['savings']['monthly_usd'] = None
                        item['savings']['evidence_available'] = False
                        item['evidence_quality'] = 'actual'
                        findings.append(item)
                    history = billing.get(resource_id, [])
                    results[resource_id] = {'resource_id': resource_id, 'status': 'available',
                        'billing_quality': quality(history), 'billing_history': history,
                        'telemetry_quality': 'actual', 'cpu_utilization_percent': cpu,
                        'datapoints_count': metric['datapoints_count'], 'recommendations': findings,
                        'reason': 'CPU-only advisory; memory, peaks and target pricing require independent review.'}
                except FAILURES:
                    continue
        except FAILURES:
            continue
    resources = [results.get(str(row['resource_id']), {'resource_id': str(row['resource_id']),
        'status': 'unavailable', 'billing_quality': 'unavailable', 'telemetry_quality': 'unavailable',
        'recommendations': [], 'reason': 'Verified instance identity and 24 hourly utilization samples are required.'}) for row in rows]
    return {'project_id': str(project_id), 'status': coverage(resources), 'resources': resources,
            'advisory_only': True, 'approval_required': True, 'window_hours': 24,
            'total_potential_monthly_savings_usd': None,
            'observed_at': datetime.now(UTC).isoformat(), 'window_end': now.isoformat()}
