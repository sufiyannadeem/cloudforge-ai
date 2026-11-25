"""Read only provenance-checked recording rules. Rich signals never reach Gemini."""
import math
import time
from uuid import UUID
from .prometheus_client import PrometheusClient

PROVENANCE='verified_resource_v1'
CANONICAL=('latency','error_rate','availability')
INTERNAL=('cpu_pressure','memory_pressure','oom','restart_loop','deployment_health',
          'latency','error_rate','availability','dependency_health','slo_violation',
          'image_pull_failure','scheduling_failure','startup_configuration')


def project_signals(project_id,client=None,*,internal=True,now=None):
    project=str(UUID(str(project_id)))
    now=time.time() if now is None else now
    names=INTERNAL if internal else CANONICAL
    prefix='cloudforge_project_internal_signal' if internal else 'cloudforge_project_signal'
    metrics=(prefix+'_state',prefix+'_observed_timestamp_seconds')
    query=f'{{__name__=~"{metrics[0]}|{metrics[1]}",project_id="{project}",provenance="{PROVENANCE}"}}'
    response=(client or PrometheusClient(timeout_seconds=2)).query(query)
    def unknown(reason):return [dict(signal=signal,state='unknown',observed_at=None,reason=reason) for signal in names]
    if response.error:return unknown('unavailable')
    rows=response.value
    if not isinstance(rows,list) or len(rows)>2*len(names):return unknown('ambiguous')
    grouped={}
    for row in rows:
        try:
            labels=row['metric']
            if (set(labels)!={'__name__','project_id','signal','provenance'} or labels['project_id']!=project
                or labels['provenance']!=PROVENANCE or labels['__name__'] not in metrics or labels['signal'] not in names):
                return unknown('untrusted_scope')
            key=(labels['signal'],labels['__name__'])
            grouped.setdefault(key,[]).append(row['value'])
        except (KeyError,TypeError):return unknown('untrusted_scope')
    result=[]
    for signal in names:
        state_rows=grouped.get((signal,metrics[0]),[])
        stamp_rows=grouped.get((signal,metrics[1]),[])
        item=dict(signal=signal,state='unknown',observed_at=None,reason='missing')
        if len(state_rows)>1 or len(stamp_rows)>1:item['reason']='ambiguous'
        elif len(state_rows)==len(stamp_rows)==1:
            try:
                state_ts,value=float(state_rows[0][0]),float(state_rows[0][1])
                stamp_ts,observed=float(stamp_rows[0][0]),float(stamp_rows[0][1])
                if not all(math.isfinite(x) for x in (state_ts,value,stamp_ts,observed)) or value not in (0,1):
                    item['reason']='invalid'
                elif not (0<=now-state_ts<=45 and 0<=now-stamp_ts<=45 and abs(state_ts-stamp_ts)<.001 and 0<=now-observed<=120):
                    item['reason']='stale'
                else:item.update(state='degraded' if value==1 else 'healthy',observed_at=observed,reason=None)
            except (IndexError,TypeError,ValueError,OverflowError):item['reason']='invalid'
        result.append(item)
    return result
