-- DBA after migrations/005_remediation_reviews.sql and 003_inference_grants.sql.
BEGIN;
REVOKE ALL ON public.aiops_remediation_reviews FROM PUBLIC,cf_inference,cf_deployment;
GRANT SELECT,INSERT ON public.aiops_remediation_reviews TO cf_aiops;
GRANT USAGE ON SEQUENCE public.aiops_remediation_reviews_id_seq TO cf_aiops;
REVOKE UPDATE,DELETE,TRUNCATE ON public.aiops_remediation_reviews FROM cf_aiops;
REVOKE ALL ON SEQUENCE public.aiops_remediation_reviews_id_seq FROM PUBLIC,cf_inference,cf_deployment;
GRANT EXECUTE ON FUNCTION public.cloudforge_remediation_contract(public.aiops_remediation_proposals) TO cf_aiops,cf_deployment;
GRANT EXECUTE ON FUNCTION public.cloudforge_remediation_current_state(text,text) TO cf_aiops,cf_deployment;
GRANT EXECUTE ON FUNCTION public.cloudforge_lock_review_incident(text,text,text) TO cf_deployment;
GRANT SELECT ON public.aiops_incident_projects TO cf_deployment;
GRANT SELECT(id,status,updated_at) ON public.aiops_incidents TO cf_deployment;
GRANT SELECT(id,created_by) ON public.projects TO cf_deployment;
GRANT SELECT(project_id,username,level) ON public.project_members TO cf_deployment;
-- Existing cf_deployment SELECT auth_users grant remains; worker cf_inference gets none.
COMMIT;
