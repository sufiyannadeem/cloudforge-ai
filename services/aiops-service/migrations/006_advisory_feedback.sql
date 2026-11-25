-- Append-only local advice feedback. Existing mutation contracts/approval engine unchanged.
BEGIN;
CREATE TABLE IF NOT EXISTS public.aiops_advisory_rejections (
 id bigserial PRIMARY KEY, incident_id varchar(64) NOT NULL REFERENCES public.aiops_incidents(id),
 project_id uuid NOT NULL REFERENCES public.projects(id), effect text NOT NULL,
 action_fingerprint text NOT NULL CHECK(action_fingerprint ~ '^[a-f0-9]{64}$'),
 resource_scope text NOT NULL, actor text NOT NULL, reason text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(incident_id,project_id,effect)
);
REVOKE ALL ON public.aiops_advisory_rejections FROM PUBLIC;
-- Parent linkage is already part of immutable approval contracts. Keep the
-- recorded alternative/evidence snapshot append-once as well.
CREATE OR REPLACE FUNCTION public.cloudforge_immutable_alternative_result()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF OLD.alternative_result IS NOT NULL AND OLD.alternative_result IS DISTINCT FROM NEW.alternative_result
 THEN RAISE EXCEPTION 'Alternative result/evidence is immutable; create a fresh recommendation'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.cloudforge_immutable_alternative_result() FROM PUBLIC;
DROP TRIGGER IF EXISTS immutable_alternative_result ON public.aiops_remediation_proposals;
CREATE TRIGGER immutable_alternative_result BEFORE UPDATE OF alternative_result ON public.aiops_remediation_proposals
 FOR EACH ROW EXECUTE FUNCTION public.cloudforge_immutable_alternative_result();
COMMIT;
