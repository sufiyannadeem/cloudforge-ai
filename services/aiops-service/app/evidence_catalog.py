"""Local, bounded advice. Text/model output never supplies actions or evidence."""
from datetime import datetime, timezone
import math
from .trusted_telemetry import CANONICAL

# Effect IDs deliberately ignore prose/parameters; infrastructure IDs reuse the
# already durable mutation rejection families. Unsupported capabilities stay advice.
CATALOG=(
 ('image_pull_failure','inspect_image','investigation',None,'Verify the approved image reference and registry reachability with the project owner; do not disclose registry credentials.'),
 ('scheduling_failure','inspect_scheduling','investigation',None,'Review approved resource requests, placement constraints and available capacity before changing configuration.'),
 ('startup_configuration','inspect_configuration','investigation',None,'Ask the authorized project owner to verify referenced configuration; never request secret values.'),
 ('startup_configuration','application_configuration','infrastructure_remediation',None,'Review an approved application configuration change with a Platform Engineer; no configuration mutation API exists.'),
 ('cpu_pressure','inspect_cpu','investigation',None,'Review CPU saturation, workload demand and configured requests/limits.'),
 ('cpu_pressure','capacity_change','infrastructure_remediation','scale_deployment','Review capacity or autoscaling with a Platform Engineer; no controlled scaling API exists.'),
 ('memory_pressure','inspect_memory','investigation',None,'Compare working-set usage with limits and investigate growth before proposing changes.'),
 ('memory_pressure','memory_configuration','infrastructure_remediation',None,'Ask a Platform Engineer to review memory settings through an approved configuration workflow; no limits mutation API exists.'),
 ('oom','inspect_oom','investigation',None,'Review verified recent termination state and compare memory demand with the application limit.'),
 ('oom','memory_configuration','infrastructure_remediation',None,'Consider an independently reviewed memory configuration change; this interface cannot execute it.'),
 ('restart_loop','inspect_startup','investigation',None,'Inspect startup, readiness and dependency prerequisites using the existing scoped diagnostics.'),
 ('restart_loop','release_restore','infrastructure_remediation','rollback_deployment','Review an approved previous release with a Platform Engineer; no controlled rollback API exists.'),
 ('deployment_health','inspect_rollout','investigation',None,'Review observed generation, desired/available replicas and verified owner-chain pod state.'),
 ('deployment_health','deployment_recovery','infrastructure_remediation','rerun_deployment','Review a verified pending deployment through the existing preview/independent approval workflow. No new restart endpoint is implied.'),
 ('latency','inspect_latency','investigation',None,'Compare the measured request latency with load and resource pressure; correlation is not causality.'),
 ('error_rate','inspect_errors','investigation',None,'Review scoped error counters and release timing without exporting logs or request/customer data.'),
 ('availability','inspect_probes','investigation',None,'Compare the actual service health probe with pod readiness and deployment health.'),
 ('dependency_health','inspect_dependencies','investigation',None,'Review the approved dependency health checks; do not expose connection strings or credentials.'),
 ('dependency_health','dependency_repair','infrastructure_remediation',None,'Escalate dependency repair to its authorized owner; no dependency mutation API is provided.'),
 ('slo_violation','inspect_slo','investigation',None,'Review the approved SLO window, coverage and error budget before considering a change.'),
)
EFFECTS=frozenset(row[1] for row in CATALOG)


def validated_ai_context(analysis,project,signals,now=None):
    """Only validated saved enums/citations can affect ranking, never permissions."""
    if not isinstance(analysis,dict):return False,set()
    now=now or datetime.now(timezone.utc)
    try:
        stamp=analysis['generated_at']
        stamp=datetime.fromisoformat(stamp.replace('Z','+00:00')) if isinstance(stamp,str) else stamp
        if (analysis.get('status')!='success' or analysis.get('provider')!='gemini'
            or analysis.get('model')!='gemini-2.5-flash' or analysis.get('diagnosis_project_id')!=project
            or analysis.get('assessment')!='alert_supported' or not 0<=(now-stamp).total_seconds()<=120):return False,set()
        current={s['signal']:s['state'] for s in signals if s['state']!='unknown'}
        cited=set()
        for citation in analysis['citations']:
            kind,signal,state=citation.split(':')
            if kind!='aggregate' or signal not in CANONICAL or state!='degraded' or current.get(signal)!=state:return False,set()
            cited.add(signal)
        return bool(cited),cited
    except (ValueError,KeyError,TypeError,AttributeError):return False,set()


def select_catalog(project,incident,signals,rejected_effects=(),analysis=None,pending_target=False,knowledge=None):
    knowledge=knowledge or {}
    now=datetime.now(timezone.utc).timestamp()
    known={}
    for s in signals:
        try:
            stamp=float(s['observed_at'])
            if s.get('state')=='degraded' and s.get('reason') is None and math.isfinite(stamp) and 0<=now-stamp<=120:
                known[s['signal']]=s
        except (KeyError,TypeError,ValueError,OverflowError):pass
    ai_valid,priorities=validated_ai_context(analysis,project,signals)
    knowledge=knowledge or {}
    corroborated=set(knowledge.get('supported_signals',[])).intersection(known)
    rejected=set(rejected_effects);items=[];seen=set()
    for signal,effect,kind,action,text in sorted(CATALOG,key=lambda row:(row[0] not in priorities,row[0] not in corroborated)):
        if signal not in known or effect in rejected or effect in seen:continue
        seen.add(effect)
        supported=action=='rerun_deployment' and pending_target
        items.append(dict(effect=effect,kind=kind,action=action,description=text,
            execution_supported=supported,advisory_only=not supported,
            requires_pe_approval=kind!='investigation',resource_scope='project:'+project,
            evidence=[f"telemetry:{signal}:{int(known[signal]['observed_at'])}"],
            knowledge_citations=[r['chunk_id'] for r in knowledge.get('references',[]) if signal in r.get('signals',[])][:5],
            selection_source='validated_ai_and_trusted_evidence' if signal in priorities else 'trusted_evidence'))
    # Acknowledgement is operational workflow, never a claim of repairing infrastructure.
    if incident.get('status')=='open' and incident.get('acknowledged_at') is None and 'incident_acknowledgement' not in rejected:
        items.append(dict(effect='incident_acknowledgement',kind='acknowledgement',action='acknowledge_incident',
            description='Acknowledge the open incident. This does not repair infrastructure.',execution_supported=True,
            advisory_only=False,requires_pe_approval=True,resource_scope=incident['id'],
            evidence=['incident:open_unacknowledged'],selection_source='trusted_incident_state'))
    return dict(diagnosis_status='validated_current' if ai_valid else 'unavailable_or_stale',items=items[:20],
                outcome='evidence_supported_options' if items else 'investigation_required',
                guidance='Review trusted evidence and escalate when no safe supported action exists. Advisory items cannot execute.')
