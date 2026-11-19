"""Safety boundaries of the real Docker recovery drill; no Docker required."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_drill', ROOT / 'scripts/test-recovery-chaos.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_faults_cannot_target_existing_resources(tmp_path, monkeypatch):
    drill = module.Drill(tmp_path)
    calls = []
    monkeypatch.setattr(drill, 'docker', lambda *args, **kw: calls.append(args))
    for action in ['kill', 'stop', 'start']:
        with pytest.raises(RuntimeError): drill.fault(action, 'cloudforge-postgres')
    with pytest.raises(RuntimeError): drill.network_fault('disconnect', 'existing', 'existing')
    assert calls == []


def test_ownership_label_required_even_for_tracked_names(tmp_path, monkeypatch):
    drill = module.Drill(tmp_path)
    name = drill.run_id + '-database'
    drill.owned.append(('container', name))
    calls = []
    def docker(*args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps([{'Config': {'Labels': {module.LABEL: 'another-run'}}}]).encode())
    monkeypatch.setattr(drill, 'docker', docker)
    with pytest.raises(RuntimeError): drill.fault('kill', name)
    assert drill.cleanup() == [name]
    assert all('rm' not in call and 'kill' not in call for call in calls)


def test_command_failure_does_not_disclose_credentials(monkeypatch):
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 1, b'', b'private-token'))
    with pytest.raises(RuntimeError) as error:
        module.command(['docker', 'private-token'])
    assert 'private-token' not in str(error.value)


def test_no_external_target_or_cloud_mutation_arguments():
    result = subprocess.run(['python3', str(ROOT / 'scripts/test-recovery-chaos.py'), '--database-url', 'postgres://existing'], capture_output=True)
    assert result.returncode == 2
    source = (ROOT / 'scripts/test-recovery-chaos.py').read_text()
    assert "'--pull=never'" in source
    assert "'--internal'" in source
    assert "'--network', 'none'" in source
    assert "recovery_target_action=pause" in source


@pytest.mark.parametrize("exception", [KeyboardInterrupt, TypeError, KeyError])
def test_interruption_and_setup_failure_record_failure_and_run_cleanup(tmp_path, monkeypatch, exception):
    output = tmp_path / 'interrupted'
    cleaned = []
    def interrupted(self):
        raise exception
    monkeypatch.setattr(module.Drill, 'run', interrupted)
    monkeypatch.setattr(module.Drill, 'cleanup', lambda self: cleaned.append(True) or [])
    monkeypatch.setattr(module.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(sys, 'argv', ['drill', '--output-dir', str(output)])
    assert module.main() == 1
    assert cleaned == [True]
    assert json.loads((output / 'evidence.json').read_text())['status'] == 'FAIL'


def test_cleanup_removes_only_label_verified_containers_and_their_anonymous_volumes(tmp_path, monkeypatch):
    drill = module.Drill(tmp_path)
    name = drill.run_id + '-service'
    drill.owned = [('container', name)]
    calls = []
    def docker(*args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps([{'Config': {'Labels': {module.LABEL: drill.run_id}}}]).encode())
    monkeypatch.setattr(drill, 'docker', docker)
    assert drill.cleanup() == []
    assert calls[-1] == ('rm', '-f', '-v', name)


def test_unpinned_image_rejected_before_docker_or_build(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    config = root / 'deploy/recovery'
    config.mkdir(parents=True)
    (config / 'postgres-image.json').write_text(json.dumps({'image_id': 'postgres:latest'}))
    monkeypatch.setattr(module, 'ROOT', root)
    drill = module.Drill(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('Unpinned image must fail before any Docker command')
    monkeypatch.setattr(drill, 'docker', forbidden)
    with pytest.raises(RuntimeError, match='immutable'):
        drill.run()


def test_recovery_image_preserves_patched_runtime_and_memory_fault_is_bounded():
    pin = json.loads((ROOT / 'deploy/recovery/postgres-image.json').read_text())
    assert pin['image_id'].startswith('sha256:') and len(pin['image_id']) == 71
    dockerfile = (ROOT / 'deploy/recovery/Postgres.Dockerfile').read_text()
    assert pin['upstream'] in dockerfile
    assert 'su-exec=0.3-r0' in dockerfile and 'FROM scratch' in dockerfile
    assert 'STOPSIGNAL SIGINT' in dockerfile and 'USER 70:70' in dockerfile
    assert 'ENTRYPOINT ["docker-entrypoint.sh"]' in dockerfile
    source = (ROOT / 'scripts/test-recovery-chaos.py').read_text()
    assert "'--memory-swap', '256m'" in source
    assert 'memory.events' in source and "result.returncode != 137" in source
    assert '--publish' not in source


def test_unexpected_failure_never_emits_pass(tmp_path, monkeypatch):
    output = tmp_path / 'unexpected'
    def crash(self):
        raise AssertionError('unexpected fixture failure')
    monkeypatch.setattr(module.Drill, 'run', crash)
    monkeypatch.setattr(module.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(sys, 'argv', ['drill', '--output-dir', str(output)])
    with pytest.raises(AssertionError):
        module.main()
    assert json.loads((output / 'evidence.json').read_text())['status'] == 'FAIL'
