"""Budget and unknown-evidence regressions; no AWS calls."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy

import pytest
from preflight_fixtures import make_evidence

ROOT=Path(__file__).resolve().parents[1]
preflight=runpy.run_path(str(ROOT/'scripts/free-plan-preflight.py'))

@pytest.fixture
def evidence():
    return make_evidence()


def test_synthetic_evidence_fails_closed_without_live_dependencies(evidence):
    result=preflight['audit'](evidence, datetime.fromisoformat(evidence['checked_at']))
    assert result['verdict']=='NO-GO'
    assert any('secret' in x for x in result['blockers'])
    assert any('fresh_signed_release' in x for x in result['blockers'])
    rows=result['scenarios']
    assert [r['arithmetic_within_cap'] for r in rows]==[True,True,False]
    assert all(not r['cap_is_enforced_by_aws'] for r in rows)
    assert float(rows[1]['envelope_total'])<=105 and float(rows[1]['credit_remaining'])>=29


@pytest.mark.parametrize('change', ['paid','unknown','stale','ten_days','new_code'])
def test_unsafe_preflight_cannot_pass(evidence, change):
    for gate in preflight['REQUIRED_GATES']:
        evidence['gates'][gate]={'status':'PASS','evidence':'synthetic test-only receipt'}
    now=datetime.fromisoformat(evidence['checked_at'])
    if change=='paid':evidence['checks']['plan']['data']['accountPlanType']='PAID'
    if change=='unknown':evidence['gates'].pop('regional_write_entitlements')
    if change=='stale':now+=timedelta(days=2)
    if change=='ten_days':evidence['requested_days']=10
    if change=='new_code':evidence['inventory']['source_sha256']['infrastructure/terraform/environments/dev/eks.tf']='0'*64
    assert preflight['audit'](evidence,now)['verdict']=='NO-GO'


def test_reserve_uses_current_balance_not_old_credit_claim(evidence):
    rows=preflight['scenarios'](evidence['cost_model'],preflight['Decimal']('100'))
    assert not rows[1]['arithmetic_within_cap']


def test_unknown_or_nonfinite_prices_are_rejected(evidence):
    model=copy.deepcopy(evidence['cost_model']);model['usd_rates']['node_hour']='NaN'
    with pytest.raises(ValueError):preflight['scenarios'](model,preflight['Decimal']('134.89'))


@pytest.mark.parametrize('kind,reason', [('aws_msk_cluster','Paid-plan'), ('aws_unknown_resource','Unreviewed')])
def test_new_service_dependencies_cannot_bypass_inventory(evidence, tmp_path, monkeypatch, kind, reason):
    folder=tmp_path/'infrastructure/terraform/environments/dev';folder.mkdir(parents=True)
    (folder/'new.tf').write_text(f'resource "{kind}" "example" {{}}')
    evidence['inventory']['source_sha256']={}
    evidence['inventory']['resources']=[]
    monkeypatch.setitem(preflight['audit'].__globals__, 'ROOT', tmp_path)
    result=preflight['audit'](evidence,datetime.fromisoformat(evidence['checked_at']))
    assert result['verdict']=='NO-GO'
    assert any(reason in item for item in result['blockers'])


@pytest.mark.parametrize('days', [6, 10, True])
def test_final_profile_refuses_extensions_and_boolean_duration(evidence, days):
    evidence.update(final_profile='five-day-preview', requested_days=days)
    result=preflight['audit'](evidence,datetime.fromisoformat(evidence['checked_at']))
    assert any('limited to five days' in x for x in result['blockers'])


def test_credit_expiry_must_cover_run_and_cleanup(evidence):
    now=datetime.fromisoformat(evidence['checked_at'])
    evidence.update(final_profile='five-day-preview',requested_days=5)
    evidence['checks']['plan']['data']['accountPlanExpirationDate']=(now+timedelta(days=4)).isoformat()
    result=preflight['audit'](evidence,now)
    assert any('entire run' in x for x in result['blockers'])


def test_billing_stop_reserves_cleanup_and_unposted_usage(evidence):
    result=preflight['audit'](evidence,datetime.fromisoformat(evidence['checked_at']))
    controls=result['billing_controls']
    assert controls['stop_at_projected_spend']=='85.00'
    assert controls['stop_at_remaining_credits']=='49.89'
    evidence['checks']['plan']['data']['accountPlanRemainingCredits']['amount']=100
    lower=preflight['audit'](evidence,datetime.fromisoformat(evidence['checked_at']))
    assert lower['billing_controls']['effective_cap']=='71.00'
    assert lower['billing_controls']['stop_at_projected_spend']=='51.00'
    assert not lower['billing_controls']['automatic_enforcement']


@pytest.mark.parametrize('case', ['small_quota','unknown_usage'])
def test_final_two_node_profile_requires_verified_quota_headroom(evidence, case):
    evidence.update(final_profile='five-day-preview',requested_days=5)
    if case=='small_quota':
        quota=next(q for q in evidence['checks']['quota_ec2_applied']['data']['Quotas'] if q['QuotaCode']=='L-1216C47A')
        quota['Value']=2
    else:
        evidence['checks']['instances']['status']='UNKNOWN'
    result=preflight['audit'](evidence,datetime.fromisoformat(evidence['checked_at']))
    assert result['two_node_quota_snapshot']['status']=='UNKNOWN_OR_INSUFFICIENT'
    assert any('vCPU quota/usage' in x for x in result['blockers'])


def test_synthetic_receipts_cannot_authorize_deployment(evidence):
    for gate in preflight['REQUIRED_GATES']:
        evidence['gates'][gate]={'status':'PASS','evidence':'synthetic only'}
    result=preflight['audit'](evidence,datetime.fromisoformat(evidence['checked_at']))
    assert result['verdict']=='NO-GO'
    assert any('Synthetic fixtures' in item for item in result['blockers'])
