-- Apply after all Go migrations and `python -m app.database` as cf_migrator.
-- Fail on missing objects; never paper over an incorrect migration order.
BEGIN;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cf_project,cf_infrastructure,cf_deployment,cf_aiops,cf_finops_project,cf_finops_audit;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM cf_project,cf_infrastructure,cf_deployment,cf_aiops,cf_finops_project,cf_finops_audit;
GRANT SELECT,INSERT,UPDATE,DELETE ON projects,project_members,auth_users,auth_sessions TO cf_project;
GRANT SELECT,INSERT ON account_admin_audit TO cf_project;
GRANT USAGE ON SEQUENCE account_admin_audit_id_seq TO cf_project;
GRANT SELECT ON projects,project_members TO cf_infrastructure,cf_deployment;
GRANT SELECT(id,created_by) ON projects TO cf_finops_project;
GRANT SELECT(project_id,username) ON project_members TO cf_finops_project;
GRANT SELECT(username,role,active) ON auth_users TO cf_deployment;
GRANT SELECT,INSERT,UPDATE,DELETE ON infrastructure_resources,infrastructure_approval_assertions,infrastructure_plan_reviews,infrastructure_ec2_attribution,terraform_drift_scans TO cf_infrastructure;
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
COMMIT;
