-- Apply after all Go migrations and `python -m app.database` as cf_migrator.
-- Fail on missing objects; never paper over an incorrect migration order.
BEGIN;
SET LOCAL ROLE cf_migrator;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cf_project,cf_infrastructure,cf_deployment,cf_aiops,cf_finops_project,cf_finops_audit,cf_drift;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM cf_project,cf_infrastructure,cf_deployment,cf_aiops,cf_finops_project,cf_finops_audit,cf_drift;
-- Table ACL revocation does not remove column ACLs. Clear old column grants too.
DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT c.relname,string_agg(format('%I',a.attname),',' ORDER BY a.attnum) AS columns
  FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
  WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') AND a.attnum>0 AND NOT a.attisdropped
  GROUP BY c.relname
 LOOP
  EXECUTE format('REVOKE ALL (%s) ON TABLE public.%I FROM PUBLIC,cf_project,cf_infrastructure,cf_deployment,cf_aiops,cf_finops_project,cf_finops_audit,cf_drift',item.columns,item.relname);
 END LOOP;
END $$;

GRANT SELECT,INSERT,UPDATE,DELETE ON projects,project_members,auth_users,auth_sessions TO cf_project;
GRANT SELECT,INSERT ON account_admin_audit TO cf_project;
GRANT USAGE ON SEQUENCE account_admin_audit_id_seq TO cf_project;
GRANT SELECT ON projects,project_members TO cf_infrastructure,cf_deployment;
GRANT SELECT(id,created_by) ON projects TO cf_finops_project;
GRANT SELECT(project_id,username) ON project_members TO cf_finops_project;
GRANT SELECT(username,role,active) ON auth_users TO cf_deployment;
GRANT SELECT,INSERT,UPDATE,DELETE ON infrastructure_resources,infrastructure_approval_assertions,infrastructure_plan_reviews,infrastructure_ec2_attribution,terraform_drift_scans,infrastructure_execution_leases,infrastructure_jobs TO cf_infrastructure;
GRANT USAGE ON SEQUENCE terraform_drift_scans_id_seq TO cf_infrastructure;
GRANT SELECT,INSERT,UPDATE,DELETE ON deployments,deployment_attempts,deployment_promotions TO cf_deployment;
GRANT SELECT,INSERT ON deployment_diagnostics TO cf_deployment;
GRANT SELECT,INSERT,UPDATE,DELETE ON aiops_incidents,aiops_incident_events,aiops_remediation_proposals,aiops_telemetry_nonces TO cf_aiops;
GRANT USAGE ON SEQUENCE aiops_incident_events_id_seq TO cf_aiops;
GRANT SELECT ON deployments TO cf_aiops;
GRANT SELECT ON aiops_remediation_proposals TO cf_deployment;
GRANT UPDATE(dispatch_consumed_at) ON aiops_remediation_proposals TO cf_deployment;
GRANT SELECT(id,project_id,environment,region,status,provider,resource_type) ON infrastructure_resources TO cf_finops_project;
GRANT SELECT ON infrastructure_ec2_attribution TO cf_finops_project;
GRANT SELECT,INSERT ON finops_anomaly_captures TO cf_finops_audit;
GRANT SELECT ON infrastructure_resources,infrastructure_plan_reviews,infrastructure_ec2_attribution,terraform_drift_scans TO cf_drift;
-- Fixed-purpose definer boundary preserves the existing row/revision lock without
-- granting the reader any UPDATE capability over resources or approval revisions.
CREATE OR REPLACE FUNCTION public.cloudforge_record_scheduled_drift(
 p_id uuid, p_revision timestamptz, p_status text, p_findings jsonb)
RETURNS TABLE(id bigint, scanned_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
 IF p_status NOT IN ('observed','unavailable') OR p_status IS NULL OR p_findings IS NULL
    OR jsonb_typeof(p_findings) <> 'array' OR pg_column_size(p_findings) > 65536 THEN
  RAISE EXCEPTION 'Invalid scheduled drift evidence';
 END IF;
 IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_findings) AS e
   WHERE jsonb_typeof(e) <> 'object' OR EXISTS (
     SELECT 1 FROM jsonb_object_keys(e) AS k
     WHERE k NOT IN ('address','type','source','severity','risk','recommendation'))) THEN
  RAISE EXCEPTION 'Unexpected scheduled drift evidence fields';
 END IF;
 RETURN QUERY INSERT INTO public.terraform_drift_scans AS evidence(resource_id,actor,status,findings)
 SELECT r.id,'service:drift-scheduler',p_status,p_findings
 FROM public.infrastructure_resources r
 WHERE r.id=p_id AND r.updated_at=p_revision AND r.status='active'
 FOR UPDATE RETURNING evidence.id,evidence.scanned_at;
END $$;
REVOKE ALL ON FUNCTION public.cloudforge_record_scheduled_drift(uuid,timestamptz,text,jsonb) FROM PUBLIC,cf_project,cf_infrastructure,cf_deployment,cf_aiops,cf_finops_project,cf_finops_audit;
GRANT EXECUTE ON FUNCTION public.cloudforge_record_scheduled_drift(uuid,timestamptz,text,jsonb) TO cf_drift;
COMMIT;
