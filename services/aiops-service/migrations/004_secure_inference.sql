-- Run as cf_migrator after project and AIOps migrations. No runtime DDL.
BEGIN;
CREATE TABLE IF NOT EXISTS public.aiops_incident_projects (
 incident_id varchar(64) PRIMARY KEY REFERENCES public.aiops_incidents(id),
 project_id uuid NOT NULL REFERENCES public.projects(id),
 verified_by text NOT NULL CHECK (length(verified_by)>0),
 verified_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- Deliberately no backfill from alert labels. Approved inventory binds each incident.
CREATE TABLE IF NOT EXISTS public.ai_inference_budget (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 reserved_paise bigint NOT NULL DEFAULT 0 CHECK(reserved_paise>=0),
 imports_complete boolean NOT NULL DEFAULT false,
 cutoff_paise integer NOT NULL DEFAULT 36000 CHECK(cutoff_paise=36000),
 maximum_paise integer NOT NULL DEFAULT 40000 CHECK(maximum_paise=40000)
);
INSERT INTO public.ai_inference_budget(singleton) VALUES(true) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS public.ai_inference_usage (
 nonce text PRIMARY KEY, body_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 reserved_paise integer NOT NULL CHECK(reserved_paise>=0)
);
CREATE INDEX IF NOT EXISTS ai_inference_usage_time ON public.ai_inference_usage(created_at);
CREATE TABLE IF NOT EXISTS public.ai_inference_imports (
 source_id text PRIMARY KEY, sha256 text NOT NULL, imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE OR REPLACE FUNCTION public.cloudforge_reserve_inference(p_nonce text,p_hash text,p_exp bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE b public.ai_inference_budget%ROWTYPE;
BEGIN
 SELECT * INTO STRICT b FROM public.ai_inference_budget WHERE singleton FOR UPDATE;
 IF NOT b.imports_complete OR p_nonce !~ '^[a-f0-9]{32}$' OR p_hash !~ '^[a-f0-9]{64}$'
    OR p_exp IS NULL OR to_timestamp(p_exp)<=clock_timestamp()
    OR to_timestamp(p_exp)>clock_timestamp()+interval '30 seconds'
    OR b.reserved_paise+100>b.cutoff_paise
    OR EXISTS(SELECT 1 FROM public.ai_inference_usage WHERE nonce=p_nonce)
    OR (SELECT count(*) FROM public.ai_inference_usage WHERE created_at>clock_timestamp()-interval '60 seconds')>=5
 THEN RETURN false; END IF;
 INSERT INTO public.ai_inference_usage(nonce,body_hash,reserved_paise) VALUES(p_nonce,p_hash,100);
 UPDATE public.ai_inference_budget SET reserved_paise=reserved_paise+100 WHERE singleton;
 RETURN true;
END $$;
REVOKE ALL ON public.aiops_incident_projects,public.ai_inference_budget,public.ai_inference_usage,public.ai_inference_imports FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cloudforge_reserve_inference(text,text,bigint) FROM PUBLIC;
COMMIT;
