BEGIN;
REVOKE ALL ON public.aiops_advisory_rejections FROM PUBLIC,cf_inference,cf_deployment;
GRANT SELECT(incident_id,project_id,effect) ON public.aiops_advisory_rejections TO cf_deployment;
GRANT SELECT,INSERT ON public.aiops_advisory_rejections TO cf_aiops;
REVOKE UPDATE,DELETE,TRUNCATE ON public.aiops_advisory_rejections FROM cf_aiops;
REVOKE ALL ON SEQUENCE public.aiops_advisory_rejections_id_seq FROM PUBLIC,cf_inference,cf_deployment;
GRANT USAGE ON SEQUENCE public.aiops_advisory_rejections_id_seq TO cf_aiops;
COMMIT;
