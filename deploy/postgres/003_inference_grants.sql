-- DBA prerequisite: REVOKE TEMPORARY ON DATABASE <database> FROM PUBLIC; explicitly grant TEMP only to approved migration/reporting principals.
-- DBA: after AIOps migrations/004_secure_inference.sql. Re-run AFTER 002_runtime_grants.sql.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='cf_inference') THEN
  CREATE ROLE cf_inference LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='cf_inference' AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
 OR EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname='cf_inference')
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE r.rolname='cf_inference')
 OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE r.rolname='cf_inference')
 OR EXISTS(SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE r.rolname='cf_inference')
 OR EXISTS(SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE r.rolname='cf_inference')
 THEN RAISE EXCEPTION 'Unsafe inference principal'; END IF;
 EXECUTE format('GRANT CONNECT ON DATABASE %I TO cf_inference',current_database());
END $$;
REVOKE ALL ON SCHEMA public FROM cf_inference;
GRANT USAGE ON SCHEMA public TO cf_inference;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cf_inference;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM cf_inference;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM cf_inference;
-- Remove historical column grants too; table REVOKE alone is insufficient.
DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT c.oid,c.relname,string_agg(format('%I',a.attname),',') AS columns
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') AND a.attnum>0 AND NOT a.attisdropped
 GROUP BY c.oid,c.relname LOOP
  EXECUTE format('REVOKE ALL (%s) ON TABLE public.%I FROM cf_inference',item.columns,item.relname);
 END LOOP;
END $$;
-- Public function execution can otherwise bypass the table boundary. Existing
-- services retain their explicit function grants from 002_runtime_grants.sql.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cloudforge_reserve_inference(text,text,bigint) TO cf_inference;
GRANT SELECT ON public.aiops_incident_projects TO cf_aiops;
GRANT SELECT(id,created_by) ON public.projects TO cf_aiops;
GRANT SELECT(project_id,username,level) ON public.project_members TO cf_aiops;
GRANT SELECT(username,role,active) ON public.auth_users TO cf_aiops;
-- Fail rather than inherit unexpected PUBLIC privileges or DDL authority.
DO $$ BEGIN
 IF has_database_privilege('cf_inference',current_database(),'CREATE,TEMP')
 OR EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
           AND has_schema_privilege('cf_inference',n.oid,'CREATE'))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND c.relkind IN ('r','p','v','m','f')
           AND (has_table_privilege('cf_inference',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege('cf_inference',c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND c.relkind='S'
           AND has_sequence_privilege('cf_inference',c.oid,'USAGE,SELECT,UPDATE'))
 OR EXISTS(SELECT 1 FROM pg_proc f JOIN pg_namespace n ON n.oid=f.pronamespace
           WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND f.prosecdef
           AND f.oid<>'public.cloudforge_reserve_inference(text,text,bigint)'::regprocedure
           AND has_schema_privilege('cf_inference',n.oid,'USAGE')
           AND has_function_privilege('cf_inference',f.oid,'EXECUTE'))
 THEN RAISE EXCEPTION 'Inference retains data, definer-function or DDL privileges; revoke PUBLIC/legacy ACLs first'; END IF;
END $$;
-- No INSERT/UPDATE/DELETE ownership grants; no inference access to incident/auth/evidence tables.
COMMIT;
-- DBA only on RDS: GRANT rds_iam TO cf_inference (IAM login role).
-- Audit PUBLIC/column/default ACLs and function grants using the release checklist.
