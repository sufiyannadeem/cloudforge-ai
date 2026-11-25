"""Local review policy. No provider, inference client, or execution imports."""
import hashlib
import json
from uuid import UUID

FAMILIES={'rerun_deployment':'deployment_recovery','restart_deployment':'deployment_recovery',
          'scale_deployment':'capacity_change','rollback_deployment':'release_restore',
          'acknowledge_incident':'incident_acknowledgement','no_action':'no_change'}


def action_family(action):
    return FAMILIES[action.value if hasattr(action,'value') else action]


def fingerprint(project,incident,action):
    # Deliberately excludes prose AND parameters/target IDs. Changing only a target,
    # replica count, timeout, reason or verb alias cannot bypass an incident rejection.
    return effect_fingerprint(project,incident,action_family(action))


def lock_incident(db,incident):
    row=db.execute('''SELECT i.id,i.status,i.acknowledged_at,b.project_id,i.ai_analysis,
        (extract(epoch FROM i.updated_at)*1000000)::bigint AS revision
        FROM aiops_incidents i JOIN aiops_incident_projects b ON b.incident_id=i.id
        WHERE i.id=%s FOR UPDATE OF i''',(incident,)).fetchone()
    if not row: raise PermissionError('Authoritative incident ownership required')
    return row


def current_state(db,incident,target):
    state={'incident_revision':incident['revision'],'incident_status':incident['status'],
           'project_id':str(incident['project_id']),'target':None}
    if target:
        if str(UUID(target))!=target: raise ValueError('Canonical target UUID required')
        row=db.execute('''SELECT id::text,project_id::text,environment,status,
            (extract(epoch FROM updated_at)*1000000)::bigint AS revision,
            image,git_commit_sha,namespace,execution_mode,strategy,created_by
            FROM deployments WHERE id=%s AND project_id=%s AND namespace=%s''',
            (target,incident['project_id'],f"cf-{incident['project_id']}")).fetchone()
        if not row: raise PermissionError('Deployment is outside the incident project')
        if not row.get('created_by'): raise PermissionError('Verified deployment requester required')
        state['target']=dict(row)
    return state


def contract(row):
    return dict(version=row['recommendation_version'],incident_id=row['incident_id'],
                project_id=str(row['project_id']),resource_scope=row['resource_scope'],action=row['action'],
                parameters=row['parameters'],target_deployment_id=row['target_deployment_id'],alternative_of=row.get('alternative_of'),
                fingerprint=row['action_fingerprint'],state=row['state_snapshot'],proposed_by=row['proposed_by'],
                policy_decision=row['policy_decision'],policy_reason=row['policy_reason'],
                expiry_epoch_us=epoch_us(row['expires_at']))


def verify_actor(db,actor,project,*,platform=False):
    membership = "m.level='maintainer'" if platform else "m.level IN ('viewer','maintainer')"
    row=db.execute(f'''SELECT u.username FROM auth_users u JOIN projects p ON p.id=%s
        WHERE u.username=%s AND u.active AND u.role=ANY(%s) AND p.created_by IS NOT NULL
          AND (p.created_by=u.username OR EXISTS(SELECT 1 FROM project_members m
            WHERE m.project_id=p.id AND m.username=u.username AND {membership}))
''',(project,actor,['platform-engineer'] if platform else ['platform-engineer','sre'])).fetchone()
    if not row: raise PermissionError('Current project-scoped reviewer identity required')


def validate_approval(row,state,actor):
    if row.get('recommendation_version',0)<=0 or row.get('approved_role')!='platform-engineer':
        raise PermissionError('Fresh Platform Engineer approval required')
    if row.get('approved_by')==row['proposed_by'] or (state.get('target') and row.get('approved_by')==state['target'].get('created_by')):
        raise PermissionError('Independent approval required; self-approval prohibited')
    if row.get('approved_contract')!=contract(row) or row['state_snapshot']!=state:
        raise PermissionError('Approval does not match the exact action or current state')
    if row['action_fingerprint']!=fingerprint(row['project_id'],row['incident_id'],row['action']):
        raise PermissionError('Action fingerprint mismatch')
    if row.get('parameters')!={}:
        raise PermissionError('Unsupported action parameters')


def select_alternative(incident,rejected_families):
    # The controlled deployment catalog has no other safe executable infrastructure
    # alternative to a rejected rerun. Do not invent rollback/restart/scaling APIs.
    # Acknowledgement is a distinct workflow-only effect supported by the existing
    # authorized operational service, and only justified for an open/unacknowledged incident.
    if (incident['status']=='open' and incident.get('acknowledged_at') is None
        and 'incident_acknowledgement' not in rejected_families):
        return 'acknowledge_incident'
    return None


def epoch_us(value):
    from datetime import datetime, timezone
    if value is None: return None
    delta=value-datetime(1970,1,1,tzinfo=timezone.utc)
    return (delta.days*86400+delta.seconds)*1000000+delta.microseconds


def ensure_not_rejected(db,row):
    family=action_family(row['action'])
    denied=db.execute("""SELECT 1 FROM aiops_remediation_proposals WHERE incident_id=%s AND action_family=%s AND status='REJECTED'
        UNION ALL SELECT 1 FROM aiops_advisory_rejections WHERE incident_id=%s AND project_id=%s AND effect=%s LIMIT 1""",
        (row['incident_id'],family,row['incident_id'],row['project_id'],family)).fetchone()
    if denied: raise PermissionError('This action effect was rejected for the incident')


def effect_fingerprint(project,incident,effect):
    return hashlib.sha256(json.dumps([str(project),incident,effect],separators=(',',':')).encode()).hexdigest()


def validate_alternative_evidence(db,row):
    """An evidence-generated infrastructure alternative cannot outlive its facts.

    Existing manual proposals/acknowledgements keep their current contracts. The
    immutable parent reference already belongs to the approved contract.
    """
    if row['action']!='rerun_deployment' or not row.get('alternative_of'):return
    import math,time
    parent=db.execute('SELECT alternative_result FROM aiops_remediation_proposals WHERE id=%s AND incident_id=%s AND project_id=%s',
                      (row['alternative_of'],row['incident_id'],row['project_id'])).fetchone()
    result=parent.get('alternative_result') if parent else None
    basis=result.get('generation_evidence') if isinstance(result,dict) else None
    try:
        stamp=float(basis['observed_at'])
        valid=(result['proposal_id']==row['id'] and basis['project_id']==str(row['project_id'])
               and basis['provenance']=='verified_resource_v1' and basis['signal']=='deployment_health'
               and basis['state']=='degraded' and math.isfinite(stamp) and 0<=time.time()-stamp<=120)
    except (KeyError,TypeError,ValueError,OverflowError):valid=False
    if not valid:raise PermissionError('Alternative evidence expired or does not match its immutable parent')
    from .trusted_telemetry import project_signals
    current=project_signals(str(row['project_id']))
    if not any(s['signal']=='deployment_health' and s['state']=='degraded' and s['observed_at'] is not None for s in current):
        raise PermissionError('Fresh trusted degradation evidence is required for this alternative')
