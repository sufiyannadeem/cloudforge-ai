-- Explicit cf_migrator migration after 004_secure_inference.sql. No runtime DDL.
BEGIN;
ALTER TABLE public.aiops_remediation_proposals
 ADD COLUMN IF NOT EXISTS recommendation_version integer NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES public.projects(id),
 ADD COLUMN IF NOT EXISTS resource_scope text,
 ADD COLUMN IF NOT EXISTS alternative_of varchar(64) REFERENCES public.aiops_remediation_proposals(id),
 ADD COLUMN IF NOT EXISTS parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
 ADD COLUMN IF NOT EXISTS action_fingerprint text,
 ADD COLUMN IF NOT EXISTS state_snapshot jsonb,
 ADD COLUMN IF NOT EXISTS approved_contract jsonb,
 ADD COLUMN IF NOT EXISTS alternative_result jsonb,
 ADD COLUMN IF NOT EXISTS action_family text GENERATED ALWAYS AS (
 CASE action WHEN 'rerun_deployment' THEN 'deployment_recovery'
 WHEN 'restart_deployment' THEN 'deployment_recovery'
 WHEN 'scale_deployment' THEN 'capacity_change'
 WHEN 'rollback_deployment' THEN 'release_restore'
 WHEN 'acknowledge_incident' THEN 'incident_acknowledgement'
 WHEN 'no_action' THEN 'no_change' ELSE 'unsupported' END) STORED;
CREATE UNIQUE INDEX IF NOT EXISTS remediation_incident_version
 ON public.aiops_remediation_proposals(incident_id,recommendation_version) WHERE recommendation_version>0;
CREATE UNIQUE INDEX IF NOT EXISTS remediation_one_alternative
 ON public.aiops_remediation_proposals(alternative_of) WHERE alternative_of IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS remediation_scoped_identity
 ON public.aiops_remediation_proposals(id,incident_id,project_id);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='remediation_scoped_parent'
 AND conrelid='public.aiops_remediation_proposals'::regclass) THEN
  ALTER TABLE public.aiops_remediation_proposals ADD CONSTRAINT remediation_scoped_parent
  FOREIGN KEY(alternative_of,incident_id,project_id)
  REFERENCES public.aiops_remediation_proposals(id,incident_id,project_id);
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS public.aiops_remediation_reviews (
 id bigserial PRIMARY KEY,
 proposal_id varchar(64) NOT NULL REFERENCES public.aiops_remediation_proposals(id),
 incident_id varchar(64) NOT NULL REFERENCES public.aiops_incidents(id),
 project_id uuid NOT NULL REFERENCES public.projects(id),
 recommendation_version integer NOT NULL,
 event_type text NOT NULL CHECK(event_type IN ('proposed','approved','rejected','alternative_exhausted','execution_claimed')),
 actor text NOT NULL CHECK(length(btrim(actor))>0), reason text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON public.aiops_remediation_reviews FROM PUBLIC;

-- Preserve legacy rejection history only where existing authoritative ownership
-- and (for deployment actions) the actual target prove the same project scope.
-- Unprovable rows remain internal/unscoped; no labels or descriptions are trusted.
UPDATE public.aiops_remediation_proposals p SET project_id=b.project_id,
 resource_scope=COALESCE(p.target_deployment_id,p.incident_id)
FROM public.aiops_incident_projects b
WHERE p.recommendation_version=0 AND p.project_id IS NULL AND p.incident_id=b.incident_id
 AND ((p.target_deployment_id IS NULL AND p.action IN ('acknowledge_incident','no_action'))
 OR EXISTS(SELECT 1 FROM public.deployments d WHERE d.id::text=p.target_deployment_id AND d.project_id=b.project_id));
INSERT INTO public.aiops_remediation_reviews(proposal_id,incident_id,project_id,recommendation_version,event_type,actor,reason,created_at)
SELECT p.id,p.incident_id,p.project_id,0,'rejected',p.rejected_by,p.rejection_reason,p.rejected_at
FROM public.aiops_remediation_proposals p WHERE p.recommendation_version=0 AND p.project_id IS NOT NULL
 AND p.rejected_at IS NOT NULL AND p.rejected_by IS NOT NULL AND length(btrim(p.rejected_by))>0
 AND NOT EXISTS(SELECT 1 FROM public.aiops_remediation_reviews r WHERE r.proposal_id=p.id AND r.recommendation_version=0 AND r.event_type='rejected');

-- Canonical JSON equality shared by AIOps and the final deployment execution gate.
CREATE OR REPLACE FUNCTION public.cloudforge_remediation_contract(p public.aiops_remediation_proposals)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
 SELECT jsonb_build_object('version',p.recommendation_version,'incident_id',p.incident_id,
  'project_id',p.project_id::text,'resource_scope',p.resource_scope,'action',p.action,'alternative_of',p.alternative_of,
  'parameters',p.parameters,'target_deployment_id',p.target_deployment_id,
  'fingerprint',p.action_fingerprint,'state',p.state_snapshot,'proposed_by',p.proposed_by,
  'policy_decision',p.policy_decision,'policy_reason',p.policy_reason,
  'expiry_epoch_us',(extract(epoch FROM p.expires_at)*1000000)::bigint)
$$;
REVOKE ALL ON FUNCTION public.cloudforge_remediation_contract(public.aiops_remediation_proposals) FROM PUBLIC;
CREATE OR REPLACE FUNCTION public.cloudforge_remediation_current_state(p_incident text,p_target text)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog AS $$
 SELECT jsonb_build_object('incident_revision',(extract(epoch FROM i.updated_at)*1000000)::bigint,
  'incident_status',i.status,'project_id',b.project_id::text,'target',
  CASE WHEN p_target IS NULL THEN NULL ELSE (SELECT jsonb_build_object(
   'id',d.id::text,'project_id',d.project_id::text,'environment',d.environment,'status',d.status,
   'revision',(extract(epoch FROM d.updated_at)*1000000)::bigint,'image',d.image,
   'git_commit_sha',d.git_commit_sha,'namespace',d.namespace,'execution_mode',d.execution_mode,'strategy',d.strategy,'created_by',d.created_by)
   FROM public.deployments d WHERE d.id::text=p_target AND d.project_id=b.project_id) END)
 FROM public.aiops_incidents i JOIN public.aiops_incident_projects b ON b.incident_id=i.id WHERE i.id=p_incident
$$;
REVOKE ALL ON FUNCTION public.cloudforge_remediation_current_state(text,text) FROM PUBLIC;
-- Read-only execution principal needs a narrow row-lock boundary, not UPDATE
-- authority on incidents. Dispatch proof is required even to acquire this lock.
CREATE OR REPLACE FUNCTION public.cloudforge_lock_review_incident(p_incident text,p_proposal text,p_dispatch_hash text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE locked text;
BEGIN
 SELECT i.id INTO locked FROM public.aiops_incidents i
 WHERE i.id=p_incident AND i.status='open' AND EXISTS(
  SELECT 1 FROM public.aiops_remediation_proposals p WHERE p.id=p_proposal
  AND p.incident_id=i.id AND p.dispatch_token_hash=p_dispatch_hash
  AND p.dispatch_consumed_at IS NULL AND p.status='EXECUTING' AND p.expires_at>clock_timestamp())
 FOR UPDATE OF i;
 RETURN locked IS NOT NULL;
END $$;
REVOKE ALL ON FUNCTION public.cloudforge_lock_review_incident(text,text,text) FROM PUBLIC;
CREATE OR REPLACE FUNCTION public.cloudforge_immutable_remediation()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF OLD.recommendation_version>0 AND
    public.cloudforge_remediation_contract(OLD) IS DISTINCT FROM public.cloudforge_remediation_contract(NEW)
 THEN RAISE EXCEPTION 'Recommendation contracts are immutable; create a fresh version'; END IF;
 IF OLD.recommendation_version>0 AND ROW(OLD.reason,OLD.created_at,OLD.alternative_of)
    IS DISTINCT FROM ROW(NEW.reason,NEW.created_at,NEW.alternative_of)
 THEN RAISE EXCEPTION 'Recommendation history and lineage are immutable'; END IF;
 IF OLD.approved_contract IS NOT NULL AND OLD.approved_contract IS DISTINCT FROM NEW.approved_contract
 THEN RAISE EXCEPTION 'Approval contracts are immutable'; END IF;
 IF OLD.approved_at IS NOT NULL AND ROW(OLD.approved_by,OLD.approved_role,OLD.approved_environment,OLD.approved_at,OLD.expires_at)
    IS DISTINCT FROM ROW(NEW.approved_by,NEW.approved_role,NEW.approved_environment,NEW.approved_at,NEW.expires_at)
 THEN RAISE EXCEPTION 'Approval identity, scope and expiry are immutable'; END IF;
 IF OLD.status IN ('REJECTED','EXPIRED','SUCCEEDED','FAILED') AND NEW.status IS DISTINCT FROM OLD.status
 THEN RAISE EXCEPTION 'Terminal review state cannot be reopened'; END IF;
 IF NEW.status='APPROVED' AND OLD.status IS DISTINCT FROM NEW.status AND
   (OLD.status<>'PENDING_APPROVAL' OR NEW.recommendation_version<=0 OR NEW.approved_role IS DISTINCT FROM 'platform-engineer'
    OR NEW.approved_by IS NULL OR NEW.approved_by=NEW.proposed_by
    OR NEW.approved_contract IS DISTINCT FROM public.cloudforge_remediation_contract(NEW)
    OR NEW.expires_at IS NULL OR NEW.expires_at<=clock_timestamp())
 THEN RAISE EXCEPTION 'Fresh independent Platform Engineer approval required'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.cloudforge_immutable_remediation() FROM PUBLIC;
DROP TRIGGER IF EXISTS immutable_remediation ON public.aiops_remediation_proposals;
CREATE TRIGGER immutable_remediation BEFORE UPDATE ON public.aiops_remediation_proposals
 FOR EACH ROW EXECUTE FUNCTION public.cloudforge_immutable_remediation();
-- Legacy approvals do not authorize the new immutable contracts. Preserve their history.
UPDATE public.aiops_remediation_proposals SET status='EXPIRED'
 WHERE recommendation_version=0 AND status IN ('APPROVED','PENDING_APPROVAL');
COMMIT;
