-- Synthetic data only. Never execute against an existing application database.
INSERT INTO auth_users(username,role,password_hash,password_salt) VALUES
 ('drill-admin','platform-engineer',decode(repeat('00',32),'hex'),decode(repeat('01',32),'hex')),
 ('drill-developer','developer',decode(repeat('00',32),'hex'),decode(repeat('02',32),'hex'));
INSERT INTO projects(id,name,repository_url,created_by) VALUES
 ('10000000-0000-4000-8000-000000000001','Recovery fixture','https://example.invalid/drill','drill-developer');
INSERT INTO project_members VALUES ('10000000-0000-4000-8000-000000000001','drill-admin','viewer');
INSERT INTO account_admin_audit(nonce,actor,action,username,project_id,level) VALUES
 ('drill-membership','drill-admin','membership','drill-developer','10000000-0000-4000-8000-000000000001','viewer');
INSERT INTO infrastructure_resources(id,name,provider,region,environment,status,terraform_directory,project_id,resource_type,requested_by) VALUES
 ('20000000-0000-4000-8000-000000000001','Recovery fixture','aws','eu-west-1','development','pending','/synthetic/no-execution','10000000-0000-4000-8000-000000000001','aws_ec2','drill-developer');
INSERT INTO infrastructure_plan_reviews(resource_id,operation,revision,plan_hash,project_id,environment,requester,submitted_by,expires_at,status,decided_by) VALUES
 ('20000000-0000-4000-8000-000000000001','apply',now(),repeat('a',64),'10000000-0000-4000-8000-000000000001','development','drill-developer','drill-developer',now()+interval '1 hour','approved','drill-admin');
INSERT INTO deployments(id,project_id,environment,image,git_commit_sha,namespace,status,created_by) VALUES
 ('30000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001','development','example.invalid/drill@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','1234567','cf-drill','failed','drill-developer');
INSERT INTO deployment_attempts(id,deployment_id,attempt_number,status,started_at,completed_at,error_message) VALUES
 ('40000000-0000-4000-8000-000000000001','30000000-0000-4000-8000-000000000001',1,'failed',now(),now(),'Synthetic failed deployment: no execution');
CREATE TABLE recovery_markers(name text PRIMARY KEY, committed_at timestamptz NOT NULL);
INSERT INTO recovery_markers VALUES ('baseline',clock_timestamp());
