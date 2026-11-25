"""Offline adversarial regression checks for the actual PR #59 Sonar findings."""
import hashlib
import io
from pathlib import Path
import runpy
import secrets
import tarfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(path):
    return runpy.run_path(str(ROOT / path))


def test_acquisition_rejects_other_lock_before_reading(tmp_path, monkeypatch):
    acquisition = module('scripts/ci/acquire-integration-inputs.py')
    monkeypatch.setenv('CI_ACQUISITION_LOCK_SHA256', 'a' * 64)
    for path in (tmp_path / 'absent.json', ROOT / 'ci/../ci/integration-acquisition.json'):
        with pytest.raises(ValueError, match='checked-in acquisition lock'):
            acquisition['load'](path)


@pytest.mark.parametrize('url', [
    'http://github.com/file', 'https://127.0.0.1/file',
    'https://169.254.169.254/latest/meta-data', 'https://github.com.evil.invalid/file',
    'https://github.com@127.0.0.1/file', 'file:///etc/passwd',
    'https://github.com:8443/file', 'https://github.com/file?redirect=evil',
    'https://github.com/\r\nheader', 'https://github.com\\@127.0.0.1/file',
])
def test_artifact_url_rejected_before_network(url, tmp_path, monkeypatch):
    acquisition = module('scripts/ci/acquire-integration-inputs.py')
    def no_opener(*args):
        pytest.fail('Invalid URL reached network setup')
    monkeypatch.setattr(acquisition['urllib'].request, 'build_opener', no_opener)
    item = dict(url=url, sha256='a' * 64, version='1', format='binary', limit_mib=1)
    with pytest.raises(ValueError):
        acquisition['fetch'](item, tmp_path / 'artifact')


def test_artifact_uses_canonical_allowlisted_url(tmp_path, monkeypatch):
    acquisition = module('scripts/ci/acquire-integration-inputs.py')
    raw = b'synthetic artifact'
    calls = []
    class Opener:
        def open(self, url, timeout):
            calls.append(url)
            return io.BytesIO(raw)
    monkeypatch.setattr(acquisition['urllib'].request, 'build_opener', lambda *args: Opener())
    item = dict(url='https://GITHUB.COM:443/path', sha256=hashlib.sha256(raw).hexdigest(),
                version='1', format='binary', limit_mib=1)
    acquisition['fetch'](item, tmp_path / 'artifact')
    assert calls == ['https://github.com/path']
    redirect = acquisition['ReviewedRedirect']()
    with pytest.raises(ValueError):
        redirect.redirect_request(None, None, 302, '', {}, 'https://127.0.0.1/private')


def test_recursive_schema_closure_preserved():
    acquisition = module('scripts/ci/acquire-integration-inputs.py')
    schema = {'$ref': '#/definitions/Node'}
    definitions = {'Node': {'type': 'object', 'properties': {'next': schema}}}
    result = acquisition['standalone'](schema, definitions)
    assert result['definitions']['Node']['properties']['next'] == schema
    assert result['definitions']['Node']['additionalProperties'] is False


def test_candidate_archive_has_only_relative_regular_entries(tmp_path):
    archive = module('scripts/ci/prepare-semantic-artifacts.py')['archive_candidate']
    candidate = tmp_path / 'candidate'
    (candidate / 'wheels').mkdir(parents=True)
    (candidate / 'wheels/one.whl').write_bytes(b'synthetic')
    first, second = tmp_path / 'first.tar.gz', tmp_path / 'second.tar.gz'
    archive(candidate, first)
    archive(candidate, second)
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first) as stream:
        member, = stream.getmembers()
        assert member.name == 'wheels/one.whl' and member.isfile()
        assert member.uid == member.gid == 0 and member.mtime == 0
    (candidate / 'escape').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='links forbidden'):
        archive(candidate, tmp_path / 'linked.tar.gz')


def test_candidate_archive_rejects_special_files(tmp_path):
    import os
    archive = module('scripts/ci/prepare-semantic-artifacts.py')['archive_candidate']
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    os.mkfifo(candidate / 'pipe')
    with pytest.raises(ValueError, match='regular files'):
        archive(candidate, tmp_path / 'fifo.tar.gz')


@pytest.mark.parametrize('name', ['../escape.json', '/tmp/escape.json', 'nested/report.json', '.json'])
def test_report_rejects_unconfined_paths(name, tmp_path, monkeypatch):
    report = module('scripts/verify-consolidated-release.py')['write_report']
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        report(name, '{}')
    assert list(tmp_path.iterdir()) == []


def test_report_is_exclusive_and_does_not_follow_links(tmp_path, monkeypatch):
    report = module('scripts/verify-consolidated-release.py')['write_report']
    monkeypatch.chdir(tmp_path)
    report('report.json', '{}')
    with pytest.raises(FileExistsError):
        report('report.json', 'changed')
    (tmp_path / 'link.json').symlink_to(tmp_path / 'report.json')
    with pytest.raises(FileExistsError):
        report('link.json', 'changed')
    assert (tmp_path / 'report.json').read_text() == '{}\n'


def test_hosted_postgres_requires_dedicated_secret():
    workflow = yaml.load((ROOT / '.github/workflows/consolidated-release-verification.yml').read_text(),
                         Loader=yaml.BaseLoader)
    job = workflow['jobs']['postgres-hosted']
    secret = '${{ secrets.SYNTHETIC_CI_POSTGRES_PASSWORD }}'
    assert job['services']['postgres']['env']['POSTGRES_PASSWORD'] == secret
    assert job['env']['CI_SYNTHETIC_POSTGRES_PASSWORD'] == secret
    for step in job['steps']:
        for key, value in step.get('env', {}).items():
            if key.endswith('DSN') or key.endswith('DATABASE_URL'):
                assert secret in value and '@127.0.0.1:' in value


def test_bootstrap_rejects_wrong_secret_and_non_synthetic_targets():
    validate = module('scripts/ci/bootstrap-integration-postgres.py')['synthetic_config']
    password = secrets.token_hex(32)
    dsn = f'postgresql://postgres:{password}@127.0.0.1:5432/postgres?sslmode=disable'
    assert validate(dsn, password)['host'] == '127.0.0.1'
    for wrong in ('', 'short', secrets.token_hex(32)):
        with pytest.raises(RuntimeError):
            validate(dsn, wrong)
    for before, after in [('127.0.0.1', 'production.invalid'), ('/postgres?', '/application?'),
                          ('sslmode=disable', 'sslmode=require')]:
        with pytest.raises(RuntimeError):
            validate(dsn.replace(before, after), password)


def test_kubernetes_patch_keeps_base_budgets_and_disables_token():
    patch = yaml.safe_load((ROOT / 'deploy/kubernetes/inference/aiops-patch.yaml').read_text())
    base = next(d for d in yaml.safe_load_all((ROOT / 'deploy/kubernetes/cloudforge-secrets-example.yml').read_text())
                if d and d.get('kind') == 'Deployment' and d['metadata']['name'] == 'aiops-service')
    spec = patch['spec']['template']['spec']
    assert spec['automountServiceAccountToken'] is False
    assert spec['containers'][0]['resources'] == base['spec']['template']['spec']['containers'][0]['resources']
    worker = next(d for d in yaml.safe_load_all((ROOT / 'deploy/kubernetes/inference/workload.yaml').read_text())
                  if d and d.get('kind') == 'Deployment')
    resources = worker['spec']['template']['spec']['containers'][0]['resources']
    assert resources['requests']['ephemeral-storage'] == '16Mi'
    assert resources['limits']['ephemeral-storage'] == '64Mi'
