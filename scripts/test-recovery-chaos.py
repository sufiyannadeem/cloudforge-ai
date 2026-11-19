#!/usr/bin/env python3
"""Destructive faults ONLY in newly created, labelled local Docker fixtures.
No production target, credentials, external image pull or cluster access supported.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'cloudforge.ai/recovery-drill'


def command(args, *, data=None, timeout=60, check=True):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        # Do not include subprocess arguments, SQL, environment or server output.
        raise RuntimeError('Local drill command failed: ' + args[0])
    return result


class Drill:
    def __init__(self, output):
        self.output = output
        self.run_id = 'cf-drill-' + uuid.uuid4().hex
        self.owned = []
        self.results = []
        self.image = None

    def docker(self, *args, **kwargs):
        return command(['docker', *args], **kwargs)

    def record(self, name, start, **evidence):
        self.results.append({'check': name, 'status': 'PASS',
                             'seconds': round(time.monotonic() - start, 3), **evidence})

    def create(self, kind, suffix, *args):
        name = self.run_id + '-' + suffix
        if kind == 'container':
            self.docker('create', '--pull=never', '--name', name,
                        '--label', LABEL + '=' + self.run_id, *args)
        elif kind == 'volume':
            self.docker('volume', 'create', '--label', LABEL + '=' + self.run_id, name)
        elif kind == 'network':
            self.docker('network', 'create', '--internal', '--label', LABEL + '=' + self.run_id, name)
        else:
            raise ValueError('Unsupported fixture kind')
        self.owned.append((kind, name))
        return name

    def assert_owned(self, kind, name):
        if (kind, name) not in self.owned or not name.startswith(self.run_id + '-'):
            raise RuntimeError('Refusing non-fixture target')
        inspected = json.loads(self.docker(kind, 'inspect', name).stdout)[0]
        labels = inspected['Config']['Labels'] if kind == 'container' else inspected['Labels']
        if labels.get(LABEL) != self.run_id:
            raise RuntimeError('Fixture ownership mismatch')

    def fault(self, action, name, *args):
        if action not in {'kill', 'stop', 'start'}:
            raise ValueError('Unsupported fault')
        self.assert_owned('container', name)
        return self.docker(action, *args, name)

    def network_fault(self, action, network, container):
        if action not in {'connect', 'disconnect'}:
            raise ValueError('Unsupported network fault')
        self.assert_owned('network', network)
        self.assert_owned('container', container)
        self.docker('network', action, network, container)

    def exec(self, container, *args, **kwargs):
        self.assert_owned('container', container)
        return self.docker('exec', '-i', container, *args, **kwargs)

    def sql(self, container, sql, database='cloudforge'):
        return self.exec(container, 'psql', '-X', '-U', 'postgres', '-d', database,
                         '-v', 'ON_ERROR_STOP=1', '-Atq', data=sql.encode()).stdout.strip()

    def wait(self, predicate, seconds=40):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
            time.sleep(.2)
        raise RuntimeError('Bounded recovery deadline exceeded')

    def fingerprint(self, container):
        tables = self.sql(container, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").decode().splitlines()
        digest = hashlib.sha256()
        for table in tables:
            name = '"' + table.replace('"', '""') + '"'
            digest.update(table.encode() + b'\n')
            digest.update(self.sql(container, f'SELECT row_to_json(t)::text FROM public.{name} t ORDER BY row_to_json(t)::text'))
        return digest.hexdigest(), len(tables)

    def http_status(self, service, path):
        # wget is from the cached PostgreSQL Alpine image, not installed/downloaded.
        result = self.exec(service, 'wget', '-S', '-O', '/dev/null', '-T', '3',
                           'http://127.0.0.1:8080' + path, check=False, timeout=8)
        match = re.search(rb'HTTP/1\.[01] ([0-9]{3})', result.stderr)
        return int(match[1]) if match else None

    def postgres(self, suffix, network, volume, password, *extra):
        name = self.create('container', suffix, '--network', network,
            '--network-alias', suffix, '--memory', '512m', '--cpus', '1',
            '--mount', f'type=volume,src={volume},dst=/var/lib/postgresql/data',
            '-e', 'POSTGRES_PASSWORD=' + password, '-e', 'POSTGRES_DB=cloudforge',
            *extra, self.image)
        self.fault('start', name)
        self.wait(lambda: self.sql(name, 'SELECT 1') == b'1')
        return name

    def run(self):
        # Inspect cached image then use immutable local ID: never pull or run a user image.
        pin = json.loads((ROOT / 'deploy/recovery/postgres-image.json').read_text())
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', pin['image_id']):
            raise RuntimeError('Expected immutable local image digest')
        self.image = self.docker('image', 'inspect', pin['image_id'], '--format', '{{.Id}}').stdout.decode().strip()
        if self.image != pin['image_id']:
            raise RuntimeError('Cached PostgreSQL image unavailable')
        self.binary = self.output / 'project-service'
        env = dict(os.environ, CGO_ENABLED='0', GOOS='linux')
        result = subprocess.run(['go', 'build', '-o', str(self.binary), './cmd/server'],
                                cwd=ROOT / 'services/project-service', env=env, capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError('Local project-service build failed')
        self.oom_binary = self.output / 'oom-helper'
        result = subprocess.run(['go', 'build', '-o', str(self.oom_binary), str(ROOT / 'scripts/fixtures/recovery-oom.go')], env=env, capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError('Local OOM fixture build failed')
        network = self.create('network', 'network')
        data = self.create('volume', 'source')
        recovery = self.create('volume', 'recovery')
        archive = self.create('volume', 'archive')
        password = secrets.token_urlsafe(32)
        mounts = ('--mount', f'type=volume,src={recovery},dst=/recovery',
                  '--mount', f'type=volume,src={archive},dst=/archive')
        self.socket = self.output / 'socket'
        self.socket.mkdir(mode=0o777)
        self.socket.chmod(0o777)  # Parent output remains 0700; only this new socket is writable.
        db = self.postgres('database', network, data, password, *mounts, '--mount', f'type=bind,src={self.socket},dst=/var/run/postgresql')
        self.assert_owned('container', db)
        # Initialize only newly created archive/basebackup mounts; server stays UID 70.
        self.docker('exec', '--user', '0', db, 'sh', '-ec', 'chown postgres:postgres /recovery /archive')
        if self.exec(db, 'id', '-u').stdout.strip() != b'70':
            raise RuntimeError('PostgreSQL must run unprivileged')
        # All changes are confined to the newly initialized synthetic database.
        self.sql(db, "ALTER SYSTEM SET wal_level='replica'; ALTER SYSTEM SET archive_mode='on'; ALTER SYSTEM SET archive_command='test ! -f /archive/%f && cp %p /archive/%f';")
        self.fault('stop', db, '--time', '10')
        self.fault('start', db)
        self.wait(lambda: self.sql(db, 'SELECT 1') == b'1')
        self.sql(db, 'CREATE TABLE schema_migrations(version text PRIMARY KEY, applied_at timestamptz DEFAULT now())')
        migration_count = 0
        for service in ('project', 'infrastructure', 'deployment'):
            for migration in sorted((ROOT / f'services/{service}-service/internal/migration/migrations').glob('*.sql')):
                sql = 'BEGIN;\n' + migration.read_text() + "\nINSERT INTO schema_migrations(version) VALUES ('" + migration.name + "'); COMMIT;"
                self.sql(db, sql)
                migration_count += 1
        if self.sql(db, 'SELECT count(*) FROM schema_migrations') != str(migration_count).encode():
            raise RuntimeError('Migration receipt mismatch')
        self.sql(db, (ROOT / 'tests/fixtures/recovery.sql').read_text())
        self.initialize_aiops(db, password)
        self.alert_transport(db, network, password)
        expected = self.fingerprint(db)
        start = time.monotonic()
        dumped = self.exec(db, 'pg_dump', '-U', 'postgres', '-Fc', 'cloudforge').stdout
        backup = self.output / 'synthetic.dump'
        backup.write_bytes(dumped)
        backup.chmod(0o600)
        dump_hash = hashlib.sha256(dumped).hexdigest()
        target_data = self.create('volume', 'logical')
        target = self.postgres('logical', network, target_data, password)
        if hashlib.sha256(backup.read_bytes()).hexdigest() != dump_hash:
            raise RuntimeError('Backup checksum mismatch')
        self.exec(target, 'pg_restore', '-U', 'postgres', '--exit-on-error', '--single-transaction', '-d', 'cloudforge', data=dumped)
        if self.fingerprint(target) != expected:
            raise RuntimeError('Restored table/data fingerprint mismatch')
        # Sequence values and constraints must work after restore, not just row counts.
        self.sql(target, "INSERT INTO account_admin_audit(nonce,actor,action,username) VALUES ('restored-next','drill-admin','verify','drill-developer')")
        self.record('logical_backup_restore', start, rpo_committed_fixture_rows_lost=0,
                    tables=expected[1], backup_sha256=dump_hash, migrations=migration_count)

        start = time.monotonic()
        self.exec(db, 'pg_basebackup', '-U', 'postgres', '-D', '/recovery/base', '-X', 'stream', '-c', 'fast', timeout=90)
        self.sql(db, "INSERT INTO recovery_markers VALUES ('wal-kept', clock_timestamp()); SELECT pg_create_restore_point('cloudforge_drill_target');")
        target_time = self.sql(db, 'SELECT clock_timestamp()').decode()
        target_expected = self.fingerprint(db)
        self.sql(db, "INSERT INTO recovery_markers VALUES ('after-target', clock_timestamp());")
        target_wal = self.sql(db, 'SELECT pg_walfile_name(pg_current_wal_insert_lsn())').decode()
        self.sql(db, 'SELECT pg_switch_wal()')
        self.wait(lambda: self.sql(db, "SELECT last_archived_wal >= '" + target_wal + "' FROM pg_stat_archiver") == b't')
        pitr_data = self.create('volume', 'pitr')
        # The helper has no network and can touch only this drill's new volumes.
        restore_start = time.monotonic()
        helper = self.create('container', 'copy-base', '--network', 'none', '--user', '0',
            '--mount', f'type=volume,src={recovery},dst=/recovery,readonly',
            '--mount', f'type=volume,src={pitr_data},dst=/target', '--entrypoint', 'sh', self.image,
            '-ec', 'cp -a /recovery/base/. /target/; touch /target/recovery.signal; chown postgres:postgres /target/recovery.signal')
        self.fault('start', helper)
        self.docker('wait', helper)
        if self.docker('inspect', helper, '--format', '{{.State.ExitCode}}').stdout.strip() != b'0':
            raise RuntimeError('Base backup copy failed')
        pitr = self.create('container', 'pitr', '--network', network, '--memory', '512m', '--cpus', '1',
            '--mount', f'type=volume,src={pitr_data},dst=/var/lib/postgresql/data',
            '--mount', f'type=volume,src={archive},dst=/archive,readonly',
            self.image, 'postgres', '-c', 'archive_mode=off', '-c', 'restore_command=cp /archive/%f %p',
            '-c', 'recovery_target_name=cloudforge_drill_target', '-c', 'recovery_target_action=pause')
        self.fault('start', pitr)
        self.wait(lambda: self.sql(pitr, 'SELECT pg_is_wal_replay_paused()') == b't')
        if self.sql(pitr, 'SELECT name FROM recovery_markers ORDER BY name') != b'baseline\nwal-kept':
            raise RuntimeError('PITR target inclusion/exclusion failed')
        if self.fingerprint(pitr) != target_expected:
            raise RuntimeError('PITR audit/data fingerprint mismatch')
        self.record('wal_point_in_time_restore', restore_start, basebackup_and_restore_seconds=round(time.monotonic()-start, 3),
                    target_time=target_time, target='cloudforge_drill_target', target_rows_lost=0,
                    intentionally_excluded_rows=1, production_rpo='UNVERIFIED')

        service = self.create('container', 'service', '--network', network, '--memory', '256m', '--memory-swap', '256m', '--cpus', '.5',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only', '--user', '65534:65534',
            '--tmpfs', '/fault:rw,noexec,nosuid,size=1m,mode=1777',
            '--mount', f'type=bind,src={self.binary},dst=/project-service,readonly',
            '--mount', f'type=bind,src={self.oom_binary},dst=/oom-helper,readonly',
            '-e', 'APP_ENV=production', '-e', 'SERVER_PORT=8080', '-e', 'SHUTDOWN_TIMEOUT_SECONDS=3',
            '-e', 'CLOUDFORGE_FRONTEND_KEY=' + secrets.token_hex(32),
            '-e', 'DATABASE_URL=postgres://postgres:' + password + '@database:5432/cloudforge?sslmode=disable',
            '--entrypoint', '/project-service', self.image)
        self.fault('start', service)
        self.wait(lambda: self.http_status(service, '/ready') == 200)
        if self.http_status(service, '/projects') != 401:
            raise RuntimeError('Unsigned API access did not fail closed')
        start = time.monotonic()
        self.fault('kill', service, '--signal', 'KILL')
        self.fault('start', service)
        self.wait(lambda: self.http_status(service, '/ready') == 200)
        self.record('service_crash_restart', start)

        before = self.fingerprint(db)
        start = time.monotonic()
        self.fault('kill', db, '--signal', 'KILL')
        self.wait(lambda: self.http_status(service, '/ready') == 503)
        if self.http_status(service, '/health') != 200:
            raise RuntimeError('Database outage incorrectly failed liveness')
        self.fault('start', db)
        self.wait(lambda: self.http_status(service, '/ready') == 200)
        if self.fingerprint(db) != before:
            raise RuntimeError('Database crash lost committed data')
        self.record('database_crash_recovery', start, ready_during_outage=503, liveness_during_outage=200)
        start = time.monotonic()
        self.network_fault('disconnect', network, service)
        try:
            self.wait(lambda: self.http_status(service, '/ready') == 503)
        finally:
            self.network_fault('connect', network, service)
        self.wait(lambda: self.http_status(service, '/ready') == 200)
        self.record('network_disconnect_recovery', start)
        start = time.monotonic()
        full = self.exec(service, 'sh', '-c', 'dd if=/dev/zero of=/fault/full bs=65536 count=64', check=False)
        if full.returncode == 0 or b'No space left' not in full.stderr:
            raise RuntimeError('Bounded filesystem exhaustion not observed')
        self.exec(service, 'rm', '/fault/full')
        if self.http_status(service, '/ready') != 200:
            raise RuntimeError('Service did not survive isolated filesystem exhaustion')
        self.record('bounded_tmpfs_exhaustion', start, scope='isolated 1MiB scratch mount; not OOM')
        self.oom_recovery(service)
        start = time.monotonic()
        self.fault('stop', service, '--time', '5')
        if self.docker('inspect', service, '--format', '{{.State.ExitCode}}').stdout.strip() != b'0':
            raise RuntimeError('Graceful shutdown did not exit cleanly')
        if self.fingerprint(db) != before:
            raise RuntimeError('Chaos altered durable data')
        self.record('graceful_shutdown_and_integrity', start, data_sha256=before[0])

    def initialize_aiops(self, db, password):
        start = time.monotonic()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('AWS_', 'CLOUDFORGE_', 'AIOPS_'))}
        proof = secrets.token_hex(32)
        self.sql(db, "CREATE TABLE recovery_drill_identity(run_id text PRIMARY KEY, proof text NOT NULL); INSERT INTO recovery_drill_identity VALUES ('" + self.run_id + "','" + proof + "')")
        env.update(CF_RECOVERY_DRILL_ID=self.run_id, CF_RECOVERY_DRILL_PROOF=proof, CF_RECOVERY_SOCKET=str(self.socket), DATABASE_URL='postgres://postgres:' + password + '@/cloudforge?host=' + str(self.socket) + '&sslmode=disable',
                   APP_ENV='production', AI_PROVIDER='disabled', AWS_EC2_METADATA_DISABLED='true',
                   AWS_SECRETS_MANAGER_ENABLED='false', CLOUDFORGE_FRONTEND_KEY=secrets.token_hex(32),
                   CLOUDFORGE_ALERTMANAGER_KEY=secrets.token_hex(32))
        result = subprocess.run([str(ROOT / 'services/aiops-service/.venv/bin/python'),
                                 str(ROOT / 'scripts/aiops-recovery-fixture.py')],
                                env=env, capture_output=True, timeout=40)
        if result.returncode:
            raise RuntimeError('AIOps schema/webhook fixture failed')
        self.record('aiops_schema_and_authenticated_webhook_recovery', start,
                    scope='real startup DDL, real PostgreSQL and ASGI HTTP; not Prometheus delivery')

    def alert_transport(self, db, network, password):
        start = time.monotonic()
        images = {}
        for name in ('cloudforge-ai-aiops-service:latest', 'prom/alertmanager:v0.28.1'):
            images[name] = self.docker('image', 'inspect', name, '--format', '{{.Id}}').stdout.decode().strip()
        key = secrets.token_hex(32)
        token_file = self.output / 'alert-token'
        token_file.write_text(key)
        token_file.chmod(0o644)  # Private 0700 parent; mounted only in the owned receiver.
        config = {'global': {'resolve_timeout': '5s'},
                  'route': {'receiver': 'aiops', 'group_by': ['alertname', 'service'],
                            'group_wait': '1s', 'group_interval': '1s', 'repeat_interval': '1h'},
                  'receivers': [{'name': 'aiops', 'webhook_configs': [{
                      'url': 'http://aiops:8090/api/v1/alerts', 'send_resolved': True,
                      'http_config': {'authorization': {'credentials_file': '/run/alert-token'}}}]}]}
        config_file = self.output / 'alertmanager.json'
        config_file.write_text(json.dumps(config))
        aiops = self.create('container', 'aiops', '--network', network, '--network-alias', 'aiops',
            '--memory', '384m', '--cpus', '1', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
            '--mount', f'type=bind,src={ROOT / "services/aiops-service/app"},dst=/app/app,readonly',
            '-e', 'DATABASE_URL=postgres://postgres:' + password + '@database:5432/cloudforge?sslmode=disable',
            '-e', 'APP_ENV=production', '-e', 'AI_PROVIDER=disabled', '-e', 'AWS_EC2_METADATA_DISABLED=true',
            '-e', 'AWS_SECRETS_MANAGER_ENABLED=false', '-e', 'CLOUDFORGE_FRONTEND_KEY=' + secrets.token_hex(32),
            '-e', 'CLOUDFORGE_ALERTMANAGER_KEY=' + key, images['cloudforge-ai-aiops-service:latest'])
        self.fault('start', aiops)
        ready = "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8090/ready',timeout=2).status == 200"
        self.wait(lambda: self.exec(aiops, 'python', '-c', ready, check=False).returncode == 0)
        receiver = self.create('container', 'alertmanager', '--network', network, '--network-alias', 'alertmanager',
            '--memory', '128m', '--cpus', '1', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--read-only', '--tmpfs', '/alertmanager:rw,noexec,nosuid,size=32m,uid=65534,gid=65534',
            '--mount', f'type=bind,src={config_file},dst=/etc/alertmanager/config.json,readonly',
            '--mount', f'type=bind,src={token_file},dst=/run/alert-token,readonly',
            '--entrypoint', '/bin/alertmanager', images['prom/alertmanager:v0.28.1'],
            '--config.file=/etc/alertmanager/config.json', '--storage.path=/alertmanager', '--cluster.listen-address=')
        self.fault('start', receiver)
        self.wait(lambda: self.exec(aiops, 'python', '-c',
            "import urllib.request; assert urllib.request.urlopen('http://alertmanager:9093/-/ready',timeout=2).status == 200", check=False).returncode == 0)
        now = datetime.now(timezone.utc)
        alert = {'labels': {'alertname': 'RecoveryDrillTransport', 'service': 'recovery-transport', 'severity': 'critical'},
                 'annotations': {'summary': 'Injected local transport verification'},
                 'startsAt': now.isoformat(), 'endsAt': (now + timedelta(minutes=5)).isoformat()}
        send = "import sys,urllib.request; r=urllib.request.Request('http://alertmanager:9093/api/v2/alerts',data=sys.stdin.buffer.read(),headers={'Content-Type':'application/json'}); assert urllib.request.urlopen(r,timeout=3).status == 200"
        self.exec(aiops, 'python', '-c', send, data=json.dumps([alert]).encode())
        status = "SELECT status FROM aiops_incidents WHERE service='recovery-transport'"
        self.wait(lambda: self.sql(db, status) == b'open')
        alert['endsAt'] = datetime.now(timezone.utc).isoformat()
        self.exec(aiops, 'python', '-c', send, data=json.dumps([alert]).encode())
        self.wait(lambda: self.sql(db, status) == b'resolved')
        events = self.sql(db, "SELECT string_agg(event_type, ',' ORDER BY id) FROM aiops_incident_events WHERE incident_id IN (SELECT id FROM aiops_incidents WHERE service='recovery-transport')")
        if b'created' not in events or b'resolved' not in events:
            raise RuntimeError('Alert delivery recovery audit missing')
        self.fault('stop', receiver, '--time', '10')
        self.fault('stop', aiops, '--time', '10')
        self.record('alertmanager_http_delivery_and_resolution', start, injected_alert=True,
                    scope='real internal HTTP, authenticated AIOps, durable incident/events; not live Prometheus scrape',
                    fixture_image_ids=list(images.values()))

    def oom_recovery(self, service):
        start = time.monotonic()
        def events():
            raw = self.exec(service, 'cat', '/sys/fs/cgroup/memory.events').stdout.decode()
            return dict(line.split() for line in raw.splitlines())
        try:
            before = int(events()['oom_kill'])
        except (RuntimeError, KeyError, ValueError):
            self.results.append({'check': 'cgroup_oom_recovery', 'status': 'BLOCKED',
                                 'reason': 'cgroup v2 memory.events unavailable'})
            return
        result = self.exec(service, '/oom-helper', check=False, timeout=20)
        state = json.loads(self.docker('container', 'inspect', service).stdout)[0]['State']
        if state['Running']:
            killed = int(events()['oom_kill']) > before
        else:
            killed = state['OOMKilled']
            self.fault('start', service)
        if not killed or result.returncode != 137:
            raise RuntimeError('Kernel OOM termination was not verified')
        self.wait(lambda: self.http_status(service, '/ready') == 200)
        self.record('cgroup_oom_recovery', start, kernel_oom_verified=True,
                    pid1_killed=state['OOMKilled'], memory_and_swap_limit_bytes=256 << 20)

    def cleanup(self):
        failures = []
        for kind, name in reversed(self.owned):
            try:
                self.assert_owned(kind, name)
                if kind == 'container':
                    self.docker('rm', '-f', '-v', name)
                else:
                    self.docker(kind, 'rm', name)
            except (RuntimeError, subprocess.TimeoutExpired):
                failures.append(name)
        return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    drill = Drill(output)
    failed = True
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        drill.run()
        failed = False
    except KeyboardInterrupt:
        failed = True
        drill.results.append({'check': 'drill_execution', 'status': 'FAIL', 'reason': 'Interrupted; cleanup attempted'})
    except (RuntimeError, subprocess.TimeoutExpired, OSError, ValueError, KeyError, TypeError) as error:
        failed = True
        drill.results.append({'check': 'drill_execution', 'status': 'FAIL', 'reason': str(error) if isinstance(error, RuntimeError) else type(error).__name__})
    finally:
        failures = drill.cleanup()
        if failures:
            failed = True
        report = {'status': 'FAIL' if failed else 'PASS', 'fixture': drill.run_id, 'image_id': drill.image, 'checks': drill.results,
                  'cleanup_failures': failures,
                  'blocked': ['live Kubernetes/GitOps recovery and failed rollout', 'live Prometheus scrape/SLO fault response',
                              'production backup encryption/retention/restore', 'AWS Terraform state and Secrets Manager recovery',
                              'multi-node storage and node failures']}
        (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
