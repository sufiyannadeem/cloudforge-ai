#!/usr/bin/env python3
"""Explicit external inputs, conservative failure analysis; never calls AWS."""
import argparse
import importlib.util
import json
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(file):return json.loads((ROOT/file).read_text())
def evaluate(catalog=None,evidence=None,now=None):
    comparator_spec=importlib.util.spec_from_file_location('comparator',ROOT/'scripts/compare-preview-capacity.py')
    comparator=importlib.util.module_from_spec(comparator_spec);comparator_spec.loader.exec_module(comparator)
    previous=comparator.compare(catalog,evidence,now)
    if not previous['options']:return previous
    spec=importlib.util.spec_from_file_location('scheduler',ROOT/'scripts/check-two-node-scheduling.py')
    scheduler=importlib.util.module_from_spec(spec);spec.loader.exec_module(scheduler)
    profile=load('deploy/preview/scheduling-profile.json')
    groups=profile['system']+profile['monitoring']+profile['applications']
    options=[]
    for instance in ('t3a.large','t3.large','m6a.large'):
        base=next(o for o in previous['options'] if o['instance_type']==instance and o['no_surge_required'] and o['scheduling_fit'])
        budget=base['derived_node_budget'];steady=base['phases']['steady'];cpu=steady['demand']['cpu_m']
        # Leave 100m/node free as a conservative sensitivity check, not an invented
        # Kubernetes scheduling requirement or a measurement of OS overhead.
        margin=dict(budget,cpu_m=budget['cpu_m']-100)
        options.append({'instance_type':instance,'five_day':base['five_day'],'input_quota_fits':base['quota_fits_input'],
          'budget_per_node':budget,'steady':steady,'scheduling_headroom_cpu_m':2*budget['cpu_m']-cpu,
          'request_occupancy_percent':round(cpu/(2*budget['cpu_m'])*100,2),
          'sensitivity_100m_spare_per_node':scheduler.placement(groups,margin),
          'startup':{'declared_request_fit':steady['feasible'],'burst_and_cold_volume_performance':'UNKNOWN; sequence startup and measure; requests are not peak CPU'},
          'cold_migration':base['phases']['cold_migration'],
          'live_migration':base['phases']['single_surge_or_live_migration'],
          'serialized_update':{'declared_peak_fit':steady['feasible'],'policy':'surge0/unavailable1, one Deployment at a time; wait for termination and both replicas Ready',
              'terminating_pods':'Replacement may stay Pending; no force-delete, no eviction/PDB/lease bypass',
              'failed_readiness':'Stop next update; roll back same Deployment at no surge after old pod resources release; no second migration'},
          'node_failure':{'fits_full_replacement':False,'reasons':['3710m cannot fit one 1930m node','hostname and zone minDomains2 prevent same-node full recovery','RWO volumes require compatible AZ and detach/attach recovery']},
          'credit_sustainability':{'mode':'not applicable' if instance=='m6a.large' else 'Standard',
              'guaranteed_total_vcpu_baseline':4 if instance=='m6a.large' else 1.2,
              'baseline_vs_requested_load':'No credit limit' if instance=='m6a.large' else 'At sustained 3.71 vCPU, spend 222.6 credits/hour, earn 72, net burn 150.6/hour; full pair bank1728 lasts at most11.47h assuming balanced usage. Fresh T3/T3a have no launch credits.',
              'runtime_acceptance':'UNKNOWN; requests do not establish actual utilization; per-node credit exhaustion may be earlier'},
          'deployment_verdict':'NO-GO'})
    return {'recommendation':'2 fixed m6a.large; one EFS controller; all six apps two replicas; no surge; maintenance migrations',
        'deployment_verdict':'NO-GO','capacity_acceptance':'CONDITIONAL declared-request fit only; 150m is insufficient evidence of safe runtime headroom',
        'input_account_evidence_at':previous['account_evidence_at'],'input_catalog_at':previous['new_catalog_at'],
        'options':options,'feature_eligibility':'UNKNOWN, including account permission to launch m6a.large; no upgrade authorized',
        'credit_reserve_usd':'29.00','spend_cap_usd':'105.00','stop_controls':'Retain $85 accrued/forecast or $49.89 remaining credits; cleanup8 + posting-lag12. Stop earlier than five days if triggered.'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);a=p.parse_args()
    try:result=evaluate(json.loads(a.catalog.read_text()),json.loads(a.evidence.read_text()))
    except (OSError,KeyError,ValueError,TypeError,AssertionError):p.exit(2,'NO-GO: missing, invalid or stale external inputs\n')
    print(json.dumps(result,indent=2));raise SystemExit(2)
