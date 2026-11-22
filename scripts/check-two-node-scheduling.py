#!/usr/bin/env python3
"""Offline CPU/memory/pod-slot placement for the proposed two-node inventory.
Not a Kubernetes scheduler, runtime benchmark, or proof of live node allocatable.
"""
import argparse
import json
from pathlib import Path


def placement(groups, node):
    used=[[0,0,0,0],[0,0,0,0]]
    extras=[]
    for group in groups:
        values=[group['cpu_m'],group['memory_mi'],1,0 if group.get('host_network') else 1]
        if group.get('spread'):
            if group['replicas']!=2:raise ValueError('Two-node spread requires exactly two replicas')
            for i in range(2):used[i]=[a+b for a,b in zip(used[i],values)]
        else:
            extras.extend([(group['name'],values)]*group['replicas'])
    limits=[node['cpu_m'],node['memory_mi'],node['pods'],node.get('pod_ips',node['pods'])]
    total=[sum(row[j] for row in used)+sum(v[j] for _,v in extras)for j in range(4)]
    reasons=[name for j,name in enumerate(['CPU','memory','pod slots','pod IPs']) if total[j]>2*limits[j] or any(row[j]>limits[j]for row in used)]
    if reasons:return {'feasible':False,'demand':dict(zip(['cpu_m','memory_mi','pods','non_host_pods'],total)),'reasons':reasons}
    extras.sort(key=lambda item:(item[1][1],item[1][0]),reverse=True)
    allocations=[]
    def search(index):
        if index==len(extras):return True
        name,values=extras[index];seen=set()
        for i in range(2):
            state=tuple(used[i])
            if state in seen:continue
            seen.add(state)
            if all(a+b<=limit for a,b,limit in zip(used[i],values,limits)):
                used[i]=[a+b for a,b in zip(used[i],values)];allocations.append({'pod':name,'node_index':i})
                if search(index+1):return True
                allocations.pop();used[i]=[a-b for a,b in zip(used[i],values)]
        return False
    feasible=search(0)
    return {'feasible':feasible,'demand':dict(zip(['cpu_m','memory_mi','pods','non_host_pods'],total)),
            'node_usage':used if feasible else None,'singleton_placement':allocations if feasible else None,
            'reasons':[] if feasible else ['No placement meets declared two-node spread and resource limits']}


def evaluate(profile):
    if profile['node_count'] != 2:
        raise ValueError('Only the reviewed two-node model is supported')
    system=profile['system']+profile['monitoring'];apps=profile['applications']
    phases={'cold_migration_max':system+[{'name':'largest-ordered-migration','replicas':1,'cpu_m':200,'memory_mi':256}],
            'steady':system+apps,
            'simultaneous_rollout':system+apps+[dict(g,replicas=1,spread=False)for g in apps],
            'serialized_infrastructure_rollout':system+apps+[{'name':'infrastructure-surge','replicas':1,'cpu_m':200,'memory_mi':256}],
            'migration_with_old_release_running':system+apps+[{'name':'largest-ordered-migration','replicas':1,'cpu_m':200,'memory_mi':256}]}
    models={}
    for model,key in [('raw_hardware_upper_bound','raw_node'),('optimistic_al2023_secondary_ip','optimistic_al2023_node')]:
        models[model]={phase:placement(groups,profile[key])for phase,groups in phases.items()}
    return {'verdict':'NO-GO','reason':'Offline model only: inspect phase feasibility; actual allocatable, sidecars, PVC zones, startup/load and failure acceptance still required.',
            'models':models,'observed_node_allocatable':False,'monitoring_storage_gi':profile['monitoring_storage_gi'],
            'does_not_validate':['runtime utilization','actual addon sidecars','RWO volume AZ binding','two-zone ASG placement','API/admission/RBAC/network/TLS','current AMI kubelet maxPods and CNI prefix mode']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True);a=p.parse_args()
    try:result=evaluate(json.loads(a.profile.read_text()))
    except (OSError,KeyError,ValueError,TypeError):p.exit(2,'NO-GO: invalid scheduling profile\n')
    print(json.dumps(result,indent=2));raise SystemExit(2)
