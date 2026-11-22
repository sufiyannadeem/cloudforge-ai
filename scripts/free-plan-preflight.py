#!/usr/bin/env python3
"""Offline, fail-closed review of captured AWS evidence. Never calls AWS or Terraform."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DENIED = ('aws_msk', 'aws_redshift', 'aws_kinesis', 'aws_memorydb', 'aws_savingsplans')
REQUIRED_GATES = (
    'service_feature_and_credit_coverage', 'regional_write_entitlements',
    'operator_role_and_restricted_access', 'controller_iam_and_pinned_images',
    'preseeded_secret_keys_and_database_bootstrap', 'private_egress_dns_and_policies',
    'node_capacity_and_standard_credit_load_test', 'fresh_signed_release',
    'bounded_usage_and_teardown_owner', 'account_wide_credit_burn_and_billing_lag',
)


def money(value):
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_CEILING))


def scenarios(model, balance):
    """No free allowances subtracted. Use worst-case RDS CPU credit accrual.

    Volumes/secrets/keys are prorated over 730h. Variable usage and cleanup are
    explicit allowances, not a claim AWS enforces a hard spending cap.
    """
    r = {key: Decimal(str(value)) for key, value in model['usd_rates'].items()}
    hourly = (r['eks_hour'] + 2*r['node_hour'] + r['rds_hour'] + r['nat_hour']
              + r['ipv4_hour'] + r['alb_hour'] + 3*r['endpoint_az_hour']
              + (60*r['gp3_gb_month'] + 20*r['rds_gp3_gb_month']
                 + 10*r['efs_gb_month'] + 3*r['kms_key_month']
                 + 16*r['secret_month']) / Decimal(730))
    if any(not value.is_finite() or value < 0 for value in r.values()):
        raise ValueError('Invalid price dimension')
    variable = Decimal(str(model['variable_allowance']))
    cleanup = Decimal(str(model['cleanup_allowance']))
    if any(not value.is_finite() or value < 0 for value in (variable, cleanup)):
        raise ValueError('Invalid allowance')
    cap = min(Decimal('105'), balance - Decimal('29'))
    result = []
    for days in (5, 6, 10):
        hours = Decimal(days*24)
        fixed = hourly*hours
        # Full 2-vCPU surplus charge is conservative; no earned-credit deduction.
        cpu = 2*r['rds_surplus_vcpu_hour']*hours
        total = fixed+cpu+variable+cleanup
        result.append({'days':days, 'fixed':money(fixed), 'rds_cpu_credit_ceiling':money(cpu),
                       'variable_allowance':money(variable), 'cleanup_allowance':money(cleanup),
                       'envelope_total':money(total), 'credit_remaining':str((balance-Decimal(money(total))).quantize(Decimal('0.01'), rounding=ROUND_FLOOR)),
                       'arithmetic_within_cap':total <= cap,
                       'cap_is_enforced_by_aws':False})
    return result


def audit(evidence, now=None):
    now = now or datetime.now(timezone.utc)
    blockers = []
    if evidence.get('fixture_only'):
        blockers.append('Synthetic fixtures are never deployment evidence')
    checked = datetime.fromisoformat(evidence['checked_at'])
    if checked.tzinfo is None or not 0 <= (now-checked).total_seconds() <= 86400:
        blockers.append('Account evidence is stale or future-dated; refresh read-only checks')
    plan_check = evidence['checks'].get('plan', {})
    plan = plan_check.get('data', {})
    if plan_check.get('status') != 'VERIFIED_READ' or plan.get('accountPlanType') != 'FREE' or plan.get('accountPlanStatus') != 'ACTIVE':
        blockers.append('Verified active FREE plan required; never upgrade')
    balance_info = plan.get('accountPlanRemainingCredits', {})
    if balance_info.get('unit') != 'USD':
        blockers.append('Verified USD credit balance required')
    balance = Decimal(str(balance_info.get('amount', 0)))
    if not balance.is_finite() or balance < 29:
        raise ValueError('Invalid or insufficient credit balance')
    expiry = datetime.fromisoformat(plan['accountPlanExpirationDate'].replace('Z','+00:00'))
    if expiry <= now:
        blockers.append('Free plan expired')
    requested = evidence.get('requested_days')
    if evidence.get('final_profile') == 'five-day-preview' and (type(requested) is not int or requested != 5):
        blockers.append('Final preview is limited to five days; extension requires a new review')
    if type(requested) is int and requested in (5, 6, 10) and expiry <= now + timedelta(days=requested, hours=12):
        blockers.append('Free plan does not cover the entire run and cleanup safety window')
    for path, expected in evidence['inventory']['source_sha256'].items():
        source = ROOT/path
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            blockers.append('Source changed since inventory: '+path)
    # A new root resource cannot disappear from a stale reviewed inventory.
    reviewed={(r['source'],r['type'],r['name']) for r in evidence['inventory']['resources']}
    for folder in ['infrastructure/terraform/bootstrap','infrastructure/terraform/environments/dev']:
        for path in (ROOT/folder).glob('*.tf'):
            for kind,name in re.findall(r'resource\s+"(aws_[a-z0-9_]+)"\s+"([a-z0-9_]+)"',path.read_text()):
                if kind.startswith(DENIED):
                    blockers.append('Excluded Paid-plan dependency: '+kind)
                if (str(path.relative_to(ROOT)),kind,name) not in reviewed:
                    blockers.append('Unreviewed resource: '+kind+'.'+name)
    for gate in REQUIRED_GATES:
        item=evidence.get('gates',{}).get(gate,{})
        if item.get('status') != 'PASS' or not item.get('evidence'):
            blockers.append(gate+': '+item.get('reason','UNKNOWN'))
    quota_snapshot = {'status':'NOT_EVALUATED', 'required_vcpu':4}
    if evidence.get('final_profile') == 'five-day-preview':
        quota_read = evidence['checks'].get('quota_ec2_applied', {})
        quotas = quota_read.get('data', {}).get('Quotas', [])
        quota = next((q for q in quotas if q.get('QuotaCode') == 'L-1216C47A'), None)
        instances = evidence['checks'].get('instances', {})
        known_empty = instances.get('status') == 'VERIFIED_READ' and instances.get('data', {}).get('Reservations') == []
        limit = Decimal(str(quota['Value'])) if quota is not None else Decimal('0')
        known_limit = quota_read.get('status') == 'VERIFIED_READ' and limit.is_finite() and limit >= 4
        quota_snapshot = {'status':'PASS' if known_limit and known_empty else 'UNKNOWN_OR_INSUFFICIENT',
                          'required_vcpu':4, 'applied_limit':str(limit), 'observed_usage_vcpu':0 if known_empty else None}
        if not known_limit or not known_empty:
            blockers.append('Final two-node vCPU quota/usage headroom is unknown or insufficient')
    costs=scenarios(evidence['cost_model'],balance)
    requested = evidence.get('requested_days')
    selected = next((row for row in costs if row['days'] == requested), None)
    if selected is None or not selected['arithmetic_within_cap']:
        blockers.append('Requested duration has no scenario within the $105 cap and $29 reserve')
    cap = min(Decimal('105'), balance - Decimal('29'))
    cleanup = Decimal(str(evidence['cost_model']['cleanup_allowance']))
    # Reserve cleanup plus a separate unposted-usage buffer before stopping intake.
    lag_buffer = Decimal('12')
    stop_spend = max(Decimal('0'), cap-cleanup-lag_buffer)
    return {'verdict':'NO-GO' if blockers else 'PREFLIGHT-PASS-NOT-DEPLOYMENT-AUTHORIZATION',
            'credit_balance':str(balance), 'spend_cap':'105.00', 'reserve_floor':'29.00',
            'two_node_quota_snapshot':quota_snapshot,
            'billing_controls':{'effective_cap':money(cap), 'cleanup_reserve':money(cleanup),
                                'billing_lag_reserve':money(lag_buffer), 'stop_at_projected_spend':money(stop_spend),
                                'stop_at_remaining_credits':money(balance-stop_spend),
                                'unknown_tax_or_usage_forecast':'STOP / NO-GO',
                                'automatic_enforcement':False},
            'scenarios':costs, 'blockers':blockers}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',required=True,type=Path)
    args=parser.parse_args()
    try:
        result=audit(json.loads(args.evidence.read_text()))
    except (KeyError,TypeError,ValueError,OSError,ArithmeticError):
        parser.exit(2,'NO-GO: missing, invalid or incomplete preflight evidence\n')
    print(json.dumps(result,indent=2))
    raise SystemExit(2 if result['blockers'] else 0)
