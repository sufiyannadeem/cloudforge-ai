#!/usr/bin/env python3
"""Compare offline preview budgets using explicit external AWS inputs; never calls AWS."""
import argparse
from datetime import datetime, timezone
import copy
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'deploy/preview'

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

scheduler = module('scheduler', 'check-two-node-scheduling.py')
costs = module('costs', 'free-plan-preflight.py')

def compare(catalog=None, evidence=None, now=None):
    if catalog is None or evidence is None:
        return {'deployment_verdict':'NO-GO','options':[], 'reason':'Explicit fresh catalog and account inputs required; no bundled observations or prices'}
    now = now or datetime.now(timezone.utc)
    for capture in (catalog, evidence):
        checked = datetime.fromisoformat(capture['checked_at'])
        if checked.tzinfo is None or not 0 <= (now-checked).total_seconds() <= 86400:
            raise ValueError('Stale or future-dated external capacity/pricing/account inputs')
    old = json.loads((OUT/'baseline-scheduling.json').read_text())
    selected = json.loads((OUT/'scheduling-profile.json').read_text())
    checks = evidence['checks']
    plan=checks['plan']
    if plan['status']!='VERIFIED_READ' or plan['data']['accountPlanRemainingCredits']['unit']!='USD':
        raise ValueError('Verified USD credit inputs required')
    balance=Decimal(str(plan['data']['accountPlanRemainingCredits']['amount']))
    if not balance.is_finite() or balance<29:raise ValueError('Invalid or insufficient credit input')
    if checks['quota_ec2_applied']['status'] != 'VERIFIED_READ' or checks['instances']['status'] != 'VERIFIED_READ':
        raise ValueError('Verified external quota and usage inputs required')
    quota = next(q['Value'] for q in checks['quota_ec2_applied']['data']['Quotas'] if q['QuotaCode']=='L-1216C47A')
    # This model requires a known-empty pool; unknown or occupied capacity is not assumed free.
    if checks['instances']['data']['Reservations'] != []:
        raise ValueError('Capacity model requires known-empty external instance usage')
    metadata = {i['InstanceType']:i for i in catalog['checks']['instance_types']['data']['InstanceTypes']}
    if any(catalog['checks'][k]['status'] != 'VERIFIED_READ' for k in ('instance_types','offered_azs')):
        raise ValueError('Verified external shapes and offerings required')
    offered = catalog['checks']['offered_azs']['data']['InstanceTypeOfferings']
    options = []
    def option(name, instance, profile, no_surge=False):
        if instance == 't3.medium':
            cpu, memory, eni, ips, rate = 2,4096,3,6,Decimal(evidence['cost_model']['usd_rates']['node_hour'])
            azs = sorted({i['Location'] for i in checks['instance_offerings']['data']['InstanceTypeOfferings'] if i['InstanceType']==instance})
        else:
            entry=catalog['checks'][instance]
            if entry['status']!='VERIFIED_READ' or len(entry['on_demand'])!=1:
                raise ValueError('Exactly one verified external price dimension required')
            dimension=entry['on_demand'][0]['rate']
            if dimension['unit']!='Hrs':raise ValueError('Hourly price required')
            rate=Decimal(dimension['pricePerUnit']['USD'])
            if not rate.is_finite() or rate<=0:raise ValueError('Finite positive price required')
            m=metadata[instance];cpu=m['VCpuInfo']['DefaultVCpus'];memory=m['MemoryInfo']['SizeInMiB']
            eni=m['NetworkInfo']['MaximumNetworkInterfaces'];ips=m['NetworkInfo']['Ipv4AddressesPerInterface']
            azs=sorted({i['Location'] for i in offered if i['InstanceType']==instance})
        pod_ips=eni*(ips-1)
        # Conservative memory reserve at kubelet maxPods=110, even when secondary-IP
        # pod capacity is lower. Actual physical RAM and bootstrap remain blockers.
        node={'cpu_m':cpu*1000-(60+10+max(0,cpu-2)*5), 'memory_mi':memory-(11*110+255)-100,
              'pods':min(110,pod_ips+2), 'pod_ips':pod_ips}
        system=profile['system']+profile['monitoring'];apps=profile['applications']
        extra={'name':'ordered-migration-or-largest-surge','replicas':1,'cpu_m':200,'memory_mi':256}
        phases={'steady':system+apps,'cold_migration':system+[extra],
                'single_surge_or_live_migration':system+apps+[extra],
                'all_app_surge':system+apps+[dict(g,replicas=1,spread=False) for g in apps]}
        result={k:scheduler.placement(v,node) for k,v in phases.items()}
        model=copy.deepcopy(evidence['cost_model']);model['usd_rates']['node_hour']=str(rate)
        cost=costs.scenarios(model,balance)[0]
        options.append({'name':name,'instance_type':instance,'nodes':2,'vcpu_required':2*cpu,'input_quota':quota,
            'quota_fits_input':2*cpu<=quota,'offered_azs':azs,'node_hour_usd':str(rate),
            'derived_node_budget':node,'phases':result,'five_day':cost,'no_surge_required':no_surge,
            'scheduling_fit':result['steady']['feasible'] and result['cold_migration']['feasible'] and (no_surge or result['all_app_surge']['feasible']),
            'launch_template_change_required':not instance.startswith(('t3.','t3a.'))})
    option('original / serialization alone','t3.medium',old,True)
    option('larger RAM, full controller HA, no surge','t3a.large',old,True)
    option('burstable comparison: one EFS controller, no surge','t3a.large',selected,True)
    option('same preview with Intel nodes','t3.large',selected,True)
    option('selected nonburstable preview','m6a.large',selected,True)
    for i in ('t3a.xlarge','t3.xlarge','m6a.xlarge','c6a.xlarge'):
        option('full controller HA and app surge',i,old)
    selective=copy.deepcopy(selected)
    selective['monitoring']=[g for g in selective['monitoring'] if g['name']!='grafana']
    selective_result=scheduler.placement(selective['system']+selective['monitoring']+selective['applications'], dict(old['optimistic_al2023_node'],pod_ips=15))
    return {'input_kind':'SYNTHETIC_TEST_ONLY' if catalog.get('fixture_only') or evidence.get('fixture_only') else 'EXTERNAL_CAPTURE_NOT_DEPLOYMENT_AUTHORIZATION','selective_medium_one_efs_controller_without_grafana':selective_result,'deployment_verdict':'NO-GO','account_evidence_at':evidence['checked_at'],
            'new_catalog_at':catalog['checked_at'],'options':options,
            'limitations':['not actual node allocatable or runtime performance','no subnet free-IP or EC2 capacity guarantee',
             'unknown eligibility/tax/credit gates inherited unchanged','no node failure tolerance at this budget; no full replica replacement on one node',
             'controller rollout surge not admitted while apps run; pinned controllers updated only in maintenance'],
            'right_sizing':'No request reductions justified without measurements. Original medium nodes fail even with serialization; removing one EFS standby still exceeds optimistic medium RAM (7336 > 7108Mi).'}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--catalog',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args()
    try: result=compare(json.loads(args.catalog.read_text()), json.loads(args.evidence.read_text()))
    except (OSError,KeyError,ValueError,TypeError,AssertionError):parser.exit(2,'NO-GO: missing, invalid or stale external capacity inputs\n')
    print(json.dumps(result,indent=2));raise SystemExit(2)
