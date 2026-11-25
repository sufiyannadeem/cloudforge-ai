from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .database import get_connection
from .remediation_models import (
    PolicyDecision,
    RemediationAction,
    RemediationProposal,
    RemediationStatus,
)


APPROVAL_TTL_MINUTES = 30


class RemediationStore:
    def create(self, *, incident_id, action, status, policy_decision, policy_reason,
               reason, target_deployment_id, proposed_by):
        from .remediation_integrity import lock_incident, verify_actor
        with get_connection() as db:
            incident = lock_incident(db, incident_id)
            verify_actor(db, proposed_by, incident['project_id'])
            return self._create_locked(db, incident, action, policy_decision, policy_reason,
                                       reason, target_deployment_id, proposed_by)

    def _create_locked(self, db, incident, action, decision, policy_reason, reason, target, actor, parent=None):
        from .remediation_integrity import action_family, current_state, fingerprint
        if action in {RemediationAction.ACKNOWLEDGE_INCIDENT, RemediationAction.NO_ACTION} and target:
            raise ValueError('Workflow actions cannot carry deployment parameters')
        from .remediation_integrity import ensure_not_rejected
        ensure_not_rejected(db,dict(incident_id=incident['id'],project_id=incident['project_id'],action=action))
        state = current_state(db, incident, target)
        if action == RemediationAction.RERUN_DEPLOYMENT and (not state['target'] or state['target']['status'] != 'pending'):
            raise PermissionError('Only an existing pending deployment in this project can be proposed')
        version = db.execute('SELECT COALESCE(MAX(recommendation_version),0)+1 AS version FROM aiops_remediation_proposals WHERE incident_id=%s',
                             (incident['id'],)).fetchone()['version']
        now = datetime.now(timezone.utc)
        ident = f"rem-{uuid4().hex}"
        status = RemediationStatus.REJECTED if decision == PolicyDecision.BLOCKED else RemediationStatus.PENDING_APPROVAL
        decision = PolicyDecision.BLOCKED if decision == PolicyDecision.BLOCKED else PolicyDecision.REQUIRES_APPROVAL
        row = db.execute('''INSERT INTO aiops_remediation_proposals
            (id,incident_id,action,status,policy_decision,policy_reason,reason,target_deployment_id,
             proposed_by,created_at,updated_at,expires_at,recommendation_version,project_id,
             resource_scope,action_fingerprint,state_snapshot,alternative_of,parameters)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
            (ident,incident['id'],action.value,status.value,decision.value,policy_reason,reason,target,
             actor,now,now,now+timedelta(minutes=APPROVAL_TTL_MINUTES),version,incident['project_id'],
             target or incident['id'],fingerprint(incident['project_id'],incident['id'],action),Jsonb(state),parent,Jsonb({}))).fetchone()
        self._review(db,row,'proposed',actor)
        self._event(db,incident['id'],'remediation_proposed','Versioned recommendation recorded.',status.value,
                    {'proposal_id':ident,'version':version,'action':action.value,'alternative_of':parent},now)
        return self._row_to_model(row)

    def _locked(self, db, proposal_id):
        from .remediation_integrity import lock_incident
        header = db.execute('SELECT incident_id FROM aiops_remediation_proposals WHERE id=%s',(proposal_id,)).fetchone()
        if not header: raise LookupError('Remediation proposal not found')
        incident = lock_incident(db,header['incident_id'])
        row = db.execute('SELECT * FROM aiops_remediation_proposals WHERE id=%s FOR UPDATE',(proposal_id,)).fetchone()
        if row.get('project_id') is None or str(row['project_id']) != str(incident['project_id']):
            raise PermissionError('Recommendation project ownership changed')
        return row,incident

    @staticmethod
    def _review(db,row,event,actor,reason=None):
        db.execute('''INSERT INTO aiops_remediation_reviews
            (proposal_id,incident_id,project_id,recommendation_version,event_type,actor,reason)
            VALUES(%s,%s,%s,%s,%s,%s,%s)''',
            (row['id'],row['incident_id'],row['project_id'],row['recommendation_version'],event,actor,reason))

    def history(self,incident_id):
        with get_connection() as db:
            return db.execute('''SELECT id,proposal_id,recommendation_version,event_type,actor,reason,created_at,NULL::text AS effect FROM aiops_remediation_reviews
                WHERE incident_id=%s AND project_id=(SELECT project_id FROM aiops_incident_projects WHERE incident_id=%s)
                UNION ALL SELECT -id AS id,NULL AS proposal_id,0 AS recommendation_version,
                'advisory_rejected' AS event_type,actor,reason,created_at,effect FROM aiops_advisory_rejections
                WHERE incident_id=%s AND project_id=(SELECT project_id FROM aiops_incident_projects WHERE incident_id=%s)
                ORDER BY created_at,id''',(incident_id,incident_id,incident_id,incident_id)).fetchall()

    def evidence_options(self,incident_id,actor):
        from .remediation_integrity import lock_incident,verify_actor
        with get_connection() as db:
            incident=lock_incident(db,incident_id)
            verify_actor(db,actor,incident['project_id'])
            return self._evidence_options(db,incident)

    def _evidence_options(self,db,incident,pending_target=False):
        from .trusted_telemetry import project_signals
        from .evidence_catalog import select_catalog
        project=str(incident['project_id'])
        effects={r['effect'] for r in db.execute('''SELECT effect FROM aiops_advisory_rejections WHERE incident_id=%s AND project_id=%s
            UNION SELECT action_family AS effect FROM aiops_remediation_proposals WHERE incident_id=%s AND status='REJECTED' ''',
            (incident['id'],project,incident['id'])).fetchall()}
        signals=project_signals(project)
        from .knowledge_config import local_signal_knowledge
        knowledge=local_signal_knowledge(project,signals)
        catalog=select_catalog(project,incident,signals,effects,incident.get('ai_analysis'),pending_target,knowledge)
        catalog['retrieval_status']=knowledge['retrieval_status']
        catalog['knowledge_references']=knowledge['references']
        return dict(project_id=project,incident_id=incident['id'],signals=signals,catalog=catalog,
                    provenance='verified_resource_v1',rejected_effects=sorted(effects),knowledge=knowledge)

    def reject_advisory(self,incident_id,actor,effect,reason=None):
        from .remediation_integrity import lock_incident,verify_actor,effect_fingerprint
        from .evidence_catalog import EFFECTS
        if effect not in EFFECTS:raise ValueError('Unknown advisory effect')
        with get_connection() as db:
            incident=lock_incident(db,incident_id);project=str(incident['project_id'])
            verify_actor(db,actor,project)
            db.execute('''INSERT INTO aiops_advisory_rejections
                (incident_id,project_id,effect,action_fingerprint,resource_scope,actor,reason)
                VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(incident_id,project_id,effect) DO NOTHING''',
                (incident_id,project,effect,effect_fingerprint(project,incident_id,effect),'project:'+project,actor,reason))
            return {'incident_id':incident_id,'effect':effect,'status':'rejected','kind':'advisory_feedback','does_not_cancel_execution':True}

    def alternative(self, proposal_id, actor):
        from .remediation_integrity import select_alternative, verify_actor
        with get_connection() as db:
            row,incident=self._locked(db,proposal_id)
            verify_actor(db,actor,incident['project_id'])
            if row['status'] != 'REJECTED': raise PermissionError('Reject this version before requesting an alternative')
            if row.get('alternative_result') is not None: return row['alternative_result']
            families={r['action_family'] for r in db.execute("SELECT action_family FROM aiops_remediation_proposals WHERE incident_id=%s AND status='REJECTED'",(row['incident_id'],)).fetchall()}
            pending=False
            if row.get('target_deployment_id'):
                from .remediation_integrity import current_state
                try:pending=current_state(db,incident,row['target_deployment_id'])['target']['status']=='pending'
                except (PermissionError,ValueError,TypeError):pass
            options=self._evidence_options(db,incident,pending)
            families.update(options['rejected_effects'])
            candidates=options['catalog']['items']
            recovery=next((item for item in candidates if item['action']=='rerun_deployment' and item['execution_supported']),None)
            candidate='rerun_deployment' if recovery else select_alternative(incident,families)
            if candidate:
                proposal=self._create_locked(db,incident,RemediationAction(candidate),PolicyDecision.REQUIRES_APPROVAL,
                    ('Trusted degraded deployment health and a verified pending target support independent review of the existing queue action.' if recovery else 'Open, unacknowledged incident supports workflow acknowledgement only; this does not fix infrastructure.'),
                    None,row['target_deployment_id'] if recovery else None,actor,parent=proposal_id)
                result={'outcome':'pending_approval','proposal_id':proposal.id,'recommendation_version':proposal.recommendation_version,
                        'kind':'infrastructure_remediation' if recovery else 'acknowledgement'}
            else:
                result={'outcome':'investigation_required','kind':'investigation','proposal_id':None,
                        'guidance':'Review project evidence and escalate to a Platform Engineer. No materially different safe mutation is supported.'}
                # Legacy rows get scope only in the audit envelope; their immutable
                # recommendation contract is never retrospectively approved.
                audit={**row,'project_id':incident['project_id']}
                self._review(db,audit,'alternative_exhausted',actor)
            if recovery:
                fact=next(s for s in options['signals'] if s['signal']=='deployment_health' and s['state']=='degraded')
                result['generation_evidence']={'provenance':'verified_resource_v1','project_id':str(incident['project_id']),
                    'signal':'deployment_health','state':'degraded','observed_at':fact['observed_at']}
            result['catalog']=options['catalog']
            result['evidence_snapshot_only']=True
            db.execute('UPDATE aiops_remediation_proposals SET alternative_result=%s WHERE id=%s',(Jsonb(result),proposal_id))
            return result

    def get(
        self,
        proposal_id: str,
    ) -> RemediationProposal | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM aiops_remediation_proposals
                WHERE id = %s
                  AND project_id = (SELECT project_id FROM aiops_incident_projects b
                                    WHERE b.incident_id = aiops_remediation_proposals.incident_id)
                """,
                (proposal_id,),
            ).fetchone()

            if row is None:
                return None

            return self._row_to_model(row)

    def list_for_incident(
        self,
        incident_id: str,
    ) -> list[RemediationProposal]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM aiops_remediation_proposals
                WHERE incident_id = %s
                  AND project_id = (SELECT project_id FROM aiops_incident_projects b
                                    WHERE b.incident_id = aiops_remediation_proposals.incident_id)
                ORDER BY created_at DESC
                """,
                (incident_id,),
            ).fetchall()

            return [
                self._row_to_model(row)
                for row in rows
            ]

    def move_to_approved(self, proposal_id, approved_by, approved_role, expected_version, expected_fingerprint):
        from .remediation_integrity import current_state, contract, verify_actor, fingerprint
        if approved_role != 'platform-engineer': raise PermissionError('Platform Engineer approval required')
        with get_connection() as db:
            row,incident=self._locked(db,proposal_id)
            verify_actor(db,approved_by,incident['project_id'],platform=True)
            from .remediation_integrity import ensure_not_rejected
            ensure_not_rejected(db,row)
            from .remediation_integrity import validate_alternative_evidence
            validate_alternative_evidence(db,row)
            if row['status'] != 'PENDING_APPROVAL': raise PermissionError('Only pending recommendations can be approved')
            if row['recommendation_version'] != expected_version or row['action_fingerprint'] != expected_fingerprint:
                raise PermissionError('Displayed recommendation version or fingerprint is stale')
            if row['proposed_by'] == approved_by: raise PermissionError('Independent approval required; self-approval prohibited')
            now=datetime.now(timezone.utc)
            if not row['expires_at'] or row['expires_at']<=now: raise PermissionError('Recommendation expired')
            if row['policy_decision'] != 'requires_approval' or row['parameters'] != {}: raise PermissionError('Unsupported approval policy or parameters')
            if row['action_fingerprint'] != fingerprint(incident['project_id'],row['incident_id'],row['action']):
                raise PermissionError('Recommendation fingerprint mismatch')
            state=current_state(db,incident,row['target_deployment_id'])
            if state.get('target') and state['target'].get('created_by') == approved_by:
                raise PermissionError('Deployment requester cannot approve their own mutation')
            if state != row['state_snapshot']: raise PermissionError('Current state changed; request a fresh recommendation')
            from .remediation_policy import RemediationPolicy
            policy=RemediationPolicy().evaluate(RemediationAction(row['action']),incident_status=incident['status'],target_deployment_id=row['target_deployment_id'])
            if not policy.executable: raise PermissionError('Current policy blocks this action')
            updated=db.execute('''UPDATE aiops_remediation_proposals SET status='APPROVED',approved_by=%s,
                approved_role=%s,approved_environment=%s,approved_at=%s,approved_contract=%s,updated_at=%s WHERE id=%s RETURNING *''',
                (approved_by,approved_role,state['target']['environment'] if state['target'] else None,
                 now,Jsonb(contract(row)),now,proposal_id)).fetchone()
            self._review(db,updated,'approved',approved_by)
            self._event(db,row['incident_id'],'remediation_approved','Independent Platform Engineer approval recorded.',updated['status'],
                        {'proposal_id':proposal_id,'version':row['recommendation_version'],'approved_by':approved_by},now)
            return self._row_to_model(updated)

    def move_to_rejected(self,proposal_id,rejected_by,reason=None):
        from .remediation_integrity import verify_actor
        with get_connection() as db:
            row,incident=self._locked(db,proposal_id)
            verify_actor(db,rejected_by,incident['project_id'])
            if row['status'] not in {'PENDING_APPROVAL','APPROVED'} or row.get('execution_idempotency_key'):
                raise PermissionError('Only unclaimed recommendations may be rejected')
            now=datetime.now(timezone.utc)
            updated=db.execute('''UPDATE aiops_remediation_proposals SET status='REJECTED',rejected_by=%s,
                rejection_reason=%s,rejected_at=%s,updated_at=%s WHERE id=%s RETURNING *''',
                (rejected_by,reason,now,now,proposal_id)).fetchone()
            self._review(db,updated,'rejected',rejected_by,reason)
            self._event(db,row['incident_id'],'remediation_rejected','Recommendation rejected; reason retained in internal review history.',
                        'REJECTED',{'proposal_id':proposal_id,'version':row['recommendation_version']},now)
            return self._row_to_model(updated)

    def claim_execution(self,proposal_id,requested_by,idempotency_key,dispatch_token_hash):
        from .remediation_integrity import current_state, validate_approval, verify_actor
        with get_connection() as db:
            row,incident=self._locked(db,proposal_id)
            verify_actor(db,requested_by,incident['project_id'],platform=True)
            from .remediation_integrity import ensure_not_rejected
            ensure_not_rejected(db,row)
            from .remediation_integrity import validate_alternative_evidence
            validate_alternative_evidence(db,row)
            verify_actor(db,row.get('approved_by'),incident['project_id'],platform=True)
            if row['status'] != 'APPROVED' or row.get('execution_idempotency_key'):
                raise PermissionError('Execution already claimed or not approved')
            now=datetime.now(timezone.utc)
            if not row['expires_at'] or row['expires_at']<=now or not row.get('approved_at') or row['approved_at']>now:
                raise PermissionError('Approval expired or invalid')
            if row.get('rejected_at') or row['policy_decision'] != 'requires_approval': raise PermissionError('Rejected or blocked action')
            validate_approval(row,current_state(db,incident,row['target_deployment_id']),requested_by)
            from .remediation_policy import RemediationPolicy
            policy=RemediationPolicy().evaluate(RemediationAction(row['action']),incident_status=incident['status'],target_deployment_id=row['target_deployment_id'])
            if not policy.executable: raise PermissionError('Current execution policy denied')
            if row['action']=='rerun_deployment' and not dispatch_token_hash: raise PermissionError('Dispatch proof required')
            updated=db.execute('''UPDATE aiops_remediation_proposals SET status='EXECUTING',execution_requested_by=%s,
                execution_idempotency_key=%s,dispatch_token_hash=%s,updated_at=%s
                WHERE id=%s AND status='APPROVED' AND execution_idempotency_key IS NULL RETURNING *''',
                (requested_by,idempotency_key,dispatch_token_hash,now,proposal_id)).fetchone()
            if not updated: raise PermissionError('Execution already claimed')
            self._review(db,updated,'execution_claimed',requested_by)
            if row['action']=='acknowledge_incident':
                if incident['status']!='open' or incident['acknowledged_at'] is not None:
                    raise PermissionError('Incident is no longer open and unacknowledged')
                db.execute("UPDATE aiops_incidents SET acknowledged_at=%s,acknowledged_by=%s,updated_at=GREATEST(%s,updated_at+interval '1 microsecond') WHERE id=%s",
                           (now,requested_by,now,row['incident_id']))
                updated=db.execute("UPDATE aiops_remediation_proposals SET status='SUCCEEDED',executed_at=%s,result=%s WHERE id=%s RETURNING *",
                           (now,Jsonb({'atomic_acknowledgement':True}),proposal_id)).fetchone()
            self._event(db,row['incident_id'],'remediation_executing','Approved action claimed by the authorized operational service.',
                        updated['status'],{'proposal_id':proposal_id,'requested_by':requested_by},now)
            return self._row_to_model(updated)

    def mark_verifying(
        self,
        proposal_id: str,
        result: dict[str, Any] | None,
    ) -> RemediationProposal | None:
        now = datetime.now(timezone.utc)
        result = result or {}

        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    status = %s,
                    result = %s,
                    verification_result = %s,
                    verification_started_at = %s,
                    updated_at = %s
                WHERE id = %s
                  AND status = %s
                RETURNING *
                """,
                (
                    RemediationStatus.VERIFYING.value,
                    Jsonb(result.get("execution", {})),
                    Jsonb(result),
                    now,
                    now,
                    proposal_id,
                    RemediationStatus.EXECUTING.value,
                ),
            ).fetchone()

            if row is None:
                return None

            self._event(
                connection,
                row["incident_id"],
                "remediation_verifying",
                (
                    f"Remediation proposal {proposal_id} "
                    "entered verification."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "action": row["action"],
                    "result": result,
                },
                now,
            )

            return self._row_to_model(row)

    def record_verification_attempt(
        self,
        proposal_id: str,
        verification_result: dict[str, Any],
    ) -> RemediationProposal | None:
        now = datetime.now(timezone.utc)

        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    verification_result = %s,
                    updated_at = %s
                WHERE id = %s
                  AND status = %s
                RETURNING *
                """,
                (
                    Jsonb(verification_result),
                    now,
                    proposal_id,
                    RemediationStatus.VERIFYING.value,
                ),
            ).fetchone()

            if row is None:
                return None

            self._event(
                connection,
                row["incident_id"],
                "remediation_verification_retryable",
                (
                    f"Remediation proposal {proposal_id} "
                    "verification is temporarily unavailable."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "action": row["action"],
                    "verification_result": verification_result,
                },
                now,
            )

            return self._row_to_model(row)

    def mark_verified(
        self,
        proposal_id: str,
        *,
        succeeded: bool,
        verification_result: dict[str, Any] | None,
        error: str | None = None,
    ) -> RemediationProposal | None:
        now = datetime.now(timezone.utc)

        status = (
            RemediationStatus.SUCCEEDED
            if succeeded
            else RemediationStatus.FAILED
        )

        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    status = %s,
                    verification_result = %s,
                    verified_at = %s,
                    error = %s,
                    executed_at = %s,
                    updated_at = %s
                WHERE id = %s
                  AND status = %s
                RETURNING *
                """,
                (
                    status.value,
                    Jsonb(verification_result or {}),
                    now,
                    error,
                    now,
                    now,
                    proposal_id,
                    RemediationStatus.VERIFYING.value,
                ),
            ).fetchone()

            if row is None:
                return None

            self._event(
                connection,
                row["incident_id"],
                (
                    "remediation_verified"
                    if succeeded
                    else "remediation_verification_failed"
                ),
                (
                    f"Remediation proposal {proposal_id} "
                    f"{status.value.lower()} after verification."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "action": row["action"],
                    "verification_result": (
                        verification_result or {}
                    ),
                    "error": error,
                },
                now,
            )

            return self._row_to_model(row)

    def mark_result(
        self,
        proposal_id: str,
        *,
        succeeded: bool,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> RemediationProposal | None:
        now = datetime.now(timezone.utc)

        status = (
            RemediationStatus.SUCCEEDED
            if succeeded
            else RemediationStatus.FAILED
        )

        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE aiops_remediation_proposals
                SET
                    status = %s,
                    result = %s,
                    error = %s,
                    executed_at = %s,
                    updated_at = %s
                WHERE id = %s
                  AND status = %s
                RETURNING *
                """,
                (
                    status.value,
                    Jsonb(result or {}),
                    error,
                    now,
                    now,
                    proposal_id,
                    RemediationStatus.EXECUTING.value,
                ),
            ).fetchone()

            if row is None:
                return None

            self._event(
                connection,
                row["incident_id"],
                (
                    "remediation_succeeded"
                    if succeeded
                    else "remediation_failed"
                ),
                (
                    f"Remediation proposal {proposal_id} "
                    f"{status.value.lower()}."
                ),
                row["status"],
                {
                    "proposal_id": proposal_id,
                    "action": row["action"],
                    "error": error,
                    "result": result or {},
                },
                now,
            )

            return self._row_to_model(row)

    @staticmethod
    def _event(
        connection: Any,
        incident_id: str,
        event_type: str,
        message: str,
        status: str,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO aiops_incident_events (
                incident_id,
                event_type,
                message,
                status,
                metadata,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                incident_id,
                event_type,
                message,
                status,
                Jsonb(metadata),
                created_at,
            ),
        )

    @staticmethod
    def _row_to_model(
        row: dict[str, Any],
    ) -> RemediationProposal:
        return RemediationProposal(
            recommendation_version=row.get('recommendation_version',0),
            project_id=str(row['project_id']) if row.get('project_id') else None,
            resource_scope=row.get('resource_scope'), action_fingerprint=row.get('action_fingerprint'),
            alternative_of=row.get('alternative_of'), parameters=row.get('parameters') or {},
            approved_role=row.get('approved_role'), state_snapshot=row.get('state_snapshot'),
            id=row["id"],
            incident_id=row["incident_id"],
            action=RemediationAction(row["action"]),
            status=RemediationStatus(row["status"]),
            policy_decision=PolicyDecision(
                row["policy_decision"]
            ),
            policy_reason=row["policy_reason"],
            reason=row["reason"],
            target_deployment_id=row[
                "target_deployment_id"
            ],
            proposed_by=row["proposed_by"],
            approved_by=row["approved_by"],
            rejected_by=row["rejected_by"],
            rejection_reason=row["rejection_reason"],
            execution_requested_by=row[
                "execution_requested_by"
            ],
            result=row["result"] or {},
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            rejected_at=row["rejected_at"],
            executed_at=row["executed_at"],
            expires_at=row["expires_at"],
            verification_started_at=row[
                "verification_started_at"
            ],
            verified_at=row["verified_at"],
            verification_result=(
                row["verification_result"] or {}
            ),
            execution_idempotency_key=row[
                "execution_idempotency_key"
            ],
        )


remediation_store = RemediationStore()
