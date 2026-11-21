#!/usr/bin/env python3
"""Real TLS/principal/migration checks on new labelled Docker fixtures only."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', ROOT/'scripts/test-recovery-chaos.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: test-database-boundaries.py NEW_OUTPUT_DIRECTORY')
    output = Path(sys.argv[1]).resolve();output.mkdir(mode=0o700)
    drill = module.Drill(output);success = False
    try:
        drill.image = json.loads((ROOT/'deploy/recovery/postgres-image.json').read_text())['image_id']
        module.command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=database',
                        '-addext','subjectAltName=DNS:database','-keyout',str(output/'server.key'),'-out',str(output/'ca.crt')])
        (output/'ca.crt').chmod(0o644)
        env = dict(os.environ, CGO_ENABLED='0',GOOS='linux')
        for service in ['project','infrastructure','deployment']:
            r=subprocess.run(['go','build','-o',str(output/service),'./cmd/server'], cwd=ROOT/f'services/{service}-service',env=env,capture_output=True,timeout=120)
            if r.returncode:raise RuntimeError('Go migration binary build failed')
        r=subprocess.run(['go','build','-o',str(output/'dbcheck'),str(ROOT/'scripts/fixtures/database-boundaries.go')],cwd=ROOT/'services/service-identity',env=env,capture_output=True,timeout=120)
        if r.returncode:raise RuntimeError('Go database checker build failed')
        network=drill.create('network','network');volume=drill.create('volume','database')
        db=drill.postgres('database',network,volume,secrets.token_hex(32),'--network-alias','wrong-host')
        for filename in ['server.key','ca.crt']:
            drill.exec(db,'sh','-ec','umask 077; cat > /var/lib/postgresql/data/'+filename,data=(output/filename).read_bytes())
        drill.sql(db,"ALTER SYSTEM SET ssl='on'; ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/data/ca.crt'; ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/data/server.key'")
        drill.exec(db,'sh','-ec','cat > /var/lib/postgresql/data/pg_hba.conf',data=b'local all all trust\nhostnossl all all all reject\nhostssl all all all scram-sha-256\n')
        drill.sql(db,(ROOT/'deploy/postgres/001_principals.sql').read_text())
        # Existing runtime DDL authority must fail closed, not survive bootstrap.
        for grant, undo in [
            ('GRANT CREATE ON SCHEMA public TO cf_deployment', 'REVOKE CREATE ON SCHEMA public FROM cf_deployment'),
            ('GRANT CREATE ON DATABASE cloudforge TO cf_deployment', 'REVOKE CREATE ON DATABASE cloudforge FROM cf_deployment'),
            ('CREATE SCHEMA boundary_owner AUTHORIZATION cf_deployment', 'DROP SCHEMA boundary_owner'),
            ('CREATE FUNCTION public.boundary_owner() RETURNS int LANGUAGE sql AS $$SELECT 1$$; ALTER FUNCTION public.boundary_owner() OWNER TO cf_deployment', 'DROP FUNCTION public.boundary_owner()'),
            ('ALTER DATABASE cloudforge OWNER TO cf_deployment', 'ALTER DATABASE cloudforge OWNER TO postgres'),
        ]:
            drill.sql(db, grant)
            try:
                result = drill.exec(db, 'psql', '-X', '-U', 'postgres', '-d', 'cloudforge',
                    '-v', 'ON_ERROR_STOP=1', '-Atq', check=False,
                    data=(ROOT/'deploy/postgres/001_principals.sql').read_bytes())
                rejected = result.returncode != 0 and b'Runtime role retains DDL authority' in result.stderr
            finally:
                drill.sql(db, undo)
            if not rejected:
                raise RuntimeError('Bootstrap accepted pre-existing runtime DDL authority')
        principals=['migrator','project','infrastructure','deployment','aiops','finops_project','finops_audit','drift']
        passwords={p:secrets.token_hex(32) for p in principals}
        for principal,password in passwords.items():drill.sql(db,f"ALTER ROLE cf_{principal} PASSWORD '{password}'")
        drill.fault('stop',db,'--time','10');drill.fault('start',db)
        drill.wait(lambda:drill.sql(db,'SELECT 1')==b'1')
        def dsn(principal,host='database',ssl='verify-full',ca='/ca.crt'):
            return f'postgres://cf_{principal}:{passwords[principal]}@{host}/cloudforge?sslmode={ssl}&sslrootcert={ca}'
        def run(suffix,image,args,principal,extra=(),expected=0):
            c=drill.create('container',suffix,'--network',network,'--memory','384m','--cpus','1',
                '--mount',f'type=bind,src={output/"ca.crt"},dst=/ca.crt,readonly',
                '-e','APP_ENV=production','-e','DATABASE_URL='+dsn(principal),*extra,image,*args)
            drill.fault('start',c);drill.docker('wait',c)
            exitcode=int(drill.docker('inspect',c,'--format','{{.State.ExitCode}}').stdout)
            if suffix=='scheduled-drift-db' and exitcode==0:
                if b'--- PASS: TestScheduledDriftDatabaseBoundary' not in drill.docker('logs',c).stdout:
                    raise RuntimeError('Scheduled database tests did not actually execute')
            if (expected==0 and exitcode!=0) or (expected!=0 and exitcode==0):
                result=drill.docker('logs',c,check=False)
                log=result.stdout+result.stderr
                for secret in passwords.values():log=log.replace(secret.encode(),b'[REDACTED]')
                (output/(suffix+'.log')).write_bytes(log)
                raise RuntimeError('Isolated database client failed: '+suffix)
        for service in ['project','infrastructure','deployment']:
            run('migrate-'+service,drill.image,['migrate'],'migrator',
                ('--mount',f'type=bind,src={output/service},dst=/migrator,readonly','--entrypoint','/migrator','-e','TERRAFORM_READ_ONLY=true'))
        if drill.sql(db,'SELECT count(*) FROM schema_migrations')!=b'23':raise RuntimeError('migration receipts mismatch')
        aiops_image=drill.docker('image','inspect',os.getenv('CLOUDFORGE_AIOPS_TEST_IMAGE','cloudforge-ai-aiops-service:latest'),'--format','{{.Id}}').stdout.decode().strip()
        run('aiops-migrate',aiops_image,['python','-m','app.database'],'migrator',
            ('--mount',f'type=bind,src={ROOT/"services/aiops-service/app"},dst=/app/app,readonly','--entrypoint',''))
        # Prove that stale column ACLs cannot survive a reviewed handoff.
        drill.sql(db,'GRANT SELECT(password_hash) ON auth_users TO cf_deployment; GRANT UPDATE(updated_at) ON infrastructure_resources TO cf_drift')
        drill.sql(db,'SET ROLE cf_migrator;\n'+(ROOT/'deploy/postgres/002_runtime_grants.sql').read_text())
        for principal in principals[1:]:
            run('check-'+principal,drill.image,[],principal,('--mount',f'type=bind,src={output/"dbcheck"},dst=/dbcheck,readonly','--entrypoint','/dbcheck','-e','CHECK_SERVICE='+principal))
        # Optional candidate-image checks exercise its native libpq/TLS and audit writes.
        if os.getenv('CLOUDFORGE_FINOPS_TEST_IMAGE'):
            finops_image=drill.docker('image','inspect',os.environ['CLOUDFORGE_FINOPS_TEST_IMAGE'],'--format','{{.Id}}').stdout.decode().strip()
            check_python="""import os,psycopg
from app.service_identity import production_database
principal=os.environ['CHECK_SERVICE']
dsn=os.environ['DATABASE_URL']
production_database(dsn,'cf_'+principal)
with psycopg.connect(dsn,connect_timeout=3) as db:
    assert db.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()[0]
    if principal=='finops_project':
        db.execute('SELECT id,project_id FROM infrastructure_resources LIMIT 1')
    else:
        row=db.execute("INSERT INTO finops_anomaly_captures VALUES (gen_random_uuid(),'123456789012','native-fixture',now(),'{}') RETURNING id").fetchone()
        assert db.execute('SELECT actor FROM finops_anomaly_captures WHERE id=%s',(row[0],)).fetchone()[0]=='native-fixture'
"""
            for principal in ['finops_project','finops_audit']:
                run('native-'+principal,finops_image,['python','-c',check_python],principal,('--entrypoint','','-e','CHECK_SERVICE='+principal))
        for name,url in [('wrong-host',dsn('deployment','wrong-host')),('unverified',dsn('deployment',ssl='require'))]:
            run('deny-'+name,drill.image,[],'deployment',('--mount',f'type=bind,src={output/"dbcheck"},dst=/dbcheck,readonly','--entrypoint','/dbcheck','-e','CHECK_SERVICE=deployment','-e','DATABASE_URL='+url),expected=1)
        proof=secrets.token_hex(32)
        drill.sql(db,"CREATE TABLE database_boundary_fixture(id text PRIMARY KEY,proof text); INSERT INTO database_boundary_fixture VALUES ('"+drill.run_id+"','"+proof+"'); GRANT SELECT ON database_boundary_fixture TO cf_drift")
        r=subprocess.run(['go','test','-c','-tags','integration','-o',str(output/'drift-tests'),'./internal/repository'],cwd=ROOT/'services/infrastructure-service',env=env,capture_output=True,timeout=120)
        if r.returncode:raise RuntimeError('Drift integration checker build failed')
        run('scheduled-drift-db',drill.image,['-test.run=TestScheduledDrift','-test.v'],'drift',
            ('--mount',f'type=bind,src={output/"drift-tests"},dst=/drift-tests,readonly','--entrypoint','/drift-tests',
             '-e','TEST_DATABASE_URL='+dsn('migrator'),'-e','CF_DB_FIXTURE_ID='+drill.run_id,'-e','CF_DB_FIXTURE_PROOF='+proof))
        # The real HTTP server starts as a non-owner with no DDL permission.
        server=drill.create('container','runtime','--network',network,'--memory','256m',
            '--mount',f'type=bind,src={output/"ca.crt"},dst=/ca.crt,readonly',
            '--mount',f'type=bind,src={output/"project"},dst=/server,readonly','--entrypoint','/server',
            '-e','APP_ENV=production','-e','DATABASE_URL='+dsn('project'),'-e','CLOUDFORGE_FRONTEND_KEY='+secrets.token_hex(32),drill.image)
        drill.fault('start',server);drill.wait(lambda:drill.http_status(server,'/ready')==200)
        if drill.http_status(server,'/projects')!=401:raise RuntimeError('API authentication bypass')
        success=True
    except Exception as error:
        print('FAIL:',str(error) if isinstance(error,RuntimeError) else type(error).__name__)
    finally:
        failures=drill.cleanup()
        report={'status':'PASS' if success and not failures else 'FAIL','fixture':drill.run_id,
                ('checks' if success else 'planned_checks'):['23 one-shot migrations','AIOps one-shot schema','7 runtime principals','pre-existing runtime DDL authority rejected','negative DDL/account/hash/session/grant checks','real verified TLS','wrong hostname and unverified TLS rejection','production non-owner HTTP startup','scheduled drift DB history/overlap/outage/stale fences'],
                'cleanup_failures':failures}
        if os.getenv('CLOUDFORGE_FINOPS_TEST_IMAGE'):
            report['native_finops_tls_and_audit']='PASS' if success else 'UNVERIFIED'
        (output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return int(not success or bool(failures))

if __name__=='__main__':raise SystemExit(main())
