from pathlib import Path
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('node_autoscaler', ROOT / 'scripts/prepare-node-autoscaler.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def inputs():
    return {'account_id': '123456789012', 'region': 'eu-west-1', 'cluster_name': 'fixture',
            'cluster_minor': '1.35', 'chart_version': '9.0.0',
            'image': 'example.invalid/autoscaler:v1.35.1@sha256:' + 'a' * 64,
            'role_arn': 'arn:aws:iam::123456789012:role/fixture-autoscaler',
            'oidc_provider_arn': 'arn:aws:iam::123456789012:oidc-provider/oidc.eks.eu-west-1.amazonaws.com/id/FIXTURE',
            'asg_arns': ['arn:aws:autoscaling:eu-west-1:123456789012:autoScalingGroup:11111111-1111-1111-1111-111111111111:autoScalingGroupName/fixture']}


def test_autoscaler_is_leader_elected_immutable_and_scoped(inputs):
    values, trust, policy = module.prepare(inputs)
    assert values['replicaCount'] == 2 and values['extraArgs']['leader-elect'] == 'true'
    assert values['image']['repository'] + ':' + values['image']['tag'] == inputs['image']
    assert values['rbac']['serviceAccount']['annotations']['eks.amazonaws.com/role-arn'] == inputs['role_arn']
    conditions = trust['Statement'][0]['Condition']['StringEquals']
    assert set(conditions.values()) == {'sts.amazonaws.com', 'system:serviceaccount:kube-system:cloudforge-node-autoscaler'}
    write = policy['Statement'][0]
    assert write['Resource'] == inputs['asg_arns']
    assert set(write['Action']) == {'autoscaling:SetDesiredCapacity', 'autoscaling:TerminateInstanceInAutoScalingGroup'}
    assert write['Condition']['StringEquals'] == {'aws:ResourceTag/k8s.io/cluster-autoscaler/enabled': 'true', 'aws:ResourceTag/k8s.io/cluster-autoscaler/fixture': 'owned'}
    assert all('iam:' not in str(statement.get('Action')) for statement in policy['Statement'])
    assert values['containerSecurityContext']['readOnlyRootFilesystem'] is True
    # The chart merges additionalLabels into pod labels: duplicate keys break Kustomize.
    assert not (set(values.get('podLabels', {})) & set(values['additionalLabels']))


@pytest.mark.parametrize('key,value', [('image', 'example.invalid/autoscaler:latest'),
    ('image', 'example.invalid/autoscaler:v1.34.1@sha256:' + 'a' * 64),
    ('role_arn', 'arn:aws:iam::999999999999:role/foreign'),
    ('asg_arns', ['*']), ('asg_arns', []), ('cluster_minor', '1.29')])
def test_invalid_or_unscoped_autoscaler_inputs_fail_closed(inputs, key, value):
    inputs[key] = value
    with pytest.raises(ValueError): module.prepare(inputs)


def test_preparation_creates_review_artifacts_and_cannot_overwrite(tmp_path, inputs):
    import json
    import subprocess
    import sys
    import yaml
    config = tmp_path / 'inputs.json'
    config.write_text(json.dumps(inputs))
    output = tmp_path / 'review'
    command = [sys.executable, str(ROOT / 'scripts/prepare-node-autoscaler.py'), '--config', str(config), '--output-dir', str(output)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert {p.name for p in output.iterdir()} == {'values.yml', 'iam-trust.json', 'iam-policy.json', 'kustomization.yml', 'reliability-patch.yml'}
    patch = yaml.safe_load((output / 'reliability-patch.yml').read_text())
    assert len(patch) == 3
    assert patch[1]['path'].endswith('/startupProbe') and patch[2]['path'].endswith('/readinessProbe')
    assert 'unused-patch-name' not in (output / 'reliability-patch.yml').read_text()
    assert subprocess.run(command, capture_output=True).returncode != 0


def test_cli_config_and_output_cannot_escape_workspace(tmp_path, monkeypatch):
    import argparse
    monkeypatch.chdir(tmp_path)
    for value in ['../outside', '/etc/passwd']:
        with pytest.raises(argparse.ArgumentTypeError): module.workspace_path(value)
    link=tmp_path/'link';link.symlink_to(tmp_path/'config')
    with pytest.raises(argparse.ArgumentTypeError): module.workspace_path(link)
