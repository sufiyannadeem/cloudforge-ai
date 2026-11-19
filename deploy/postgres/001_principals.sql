-- Explicit DBA bootstrap, NOT an application migration. No passwords are embedded.
-- Only a fresh/approved database: existing ownership/grants require a reviewed handoff.
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['cf_migrator','cf_project','cf_infrastructure','cf_deployment','cf_aiops','cf_finops_project','cf_finops_audit','cf_drift'] LOOP
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=name) THEN
   EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL',name);
  ELSE
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=name AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN
    RAISE EXCEPTION 'Unsafe existing service principal; review before bootstrap';
   END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=name) THEN
   RAISE EXCEPTION 'Service role has inherited/set-role privileges; review required';
  END IF;
  IF name <> 'cf_migrator' AND EXISTS (SELECT 1 FROM pg_class c JOIN pg_roles r ON c.relowner=r.oid WHERE r.rolname=name) THEN
   RAISE EXCEPTION 'Runtime role owns schema objects; reviewed ownership handoff required';
  END IF;
  IF name <> 'cf_migrator' AND (
   has_database_privilege(name,current_database(),'CREATE') OR
   EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND has_schema_privilege(name,n.oid,'CREATE')) OR
   EXISTS (SELECT 1 FROM pg_namespace n JOIN pg_roles r ON n.nspowner=r.oid WHERE r.rolname=name) OR
   EXISTS (SELECT 1 FROM pg_proc p JOIN pg_roles r ON p.proowner=r.oid WHERE r.rolname=name) OR
   EXISTS (SELECT 1 FROM pg_database d JOIN pg_roles r ON d.datdba=r.oid WHERE r.rolname=name)
  ) THEN
   RAISE EXCEPTION 'Runtime role retains DDL authority; reviewed ownership/grant handoff required';
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I',current_database(),name);
 END LOOP;
END $$;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO cf_migrator;
GRANT USAGE ON SCHEMA public TO cf_project,cf_infrastructure,cf_deployment,cf_aiops,cf_finops_project,cf_finops_audit,cf_drift;
-- Migration owner creates no automatic blanket/default runtime grants.
ALTER DEFAULT PRIVILEGES FOR ROLE cf_migrator IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE cf_migrator IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
