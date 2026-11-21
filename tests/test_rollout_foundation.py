from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_rollout_rbac_never_grants_templates_or_analysis_creation():
    role, binding = yaml.safe_load_all((ROOT / 'deploy/kubernetes/project-rollout-rbac-example.yml').read_text())
    assert role['kind'] == 'Role'
    assert role['metadata']['namespace'] == binding['metadata']['namespace'] == 'cf-PROJECT_UUID'
    permissions = {tuple(rule['resources']): rule for rule in role['rules']}
    assert set(permissions[('rollouts',)]['verbs']) == {'get', 'create', 'patch'}
    assert set(permissions[('rollouts/status',)]['verbs']) == {'get', 'patch'}
    assert permissions[('analysistemplates',)]['verbs'] == ['get']
    assert permissions[('analysistemplates',)]['resourceNames'] == ['cloudforge-release-health']
    assert len(permissions) == 3
    assert binding['subjects'] == [{'kind': 'ServiceAccount', 'name': 'cloudforge-deployment-service', 'namespace': 'cloudforge'}]


def test_analysis_is_disabled_until_verified_and_fails_on_empty_or_invalid_evidence():
    template = yaml.safe_load((ROOT / 'deploy/kubernetes/rollout-analysis-template.example.yml').read_text())
    assert template['metadata']['annotations']['cloudforge.ai/evidence-verified'] == 'false'
    assert {arg['name'] for arg in template['spec']['args']} == {'namespace', 'revision'}
    for metric in template['spec']['metrics']:
        assert metric['count'] == 5 and metric['failureLimit'] == 0 and metric['consecutiveErrorLimit'] == 1
        assert metric['successCondition'].startswith('len(result) == 1 &&')
        assert metric['failureCondition'].startswith('len(result) != 1 || !(')
        assert set(metric['provider']) == {'prometheus'}
        query = metric['provider']['prometheus']['query']
        assert '{{args.namespace}}' in query and '{{args.revision}}' in query
        assert 'time() - 60' in query and 'or vector(0)' not in query


def test_prometheus_fixture_queries_match_the_actual_analysis_template():
    template = yaml.safe_load((ROOT / 'deploy/kubernetes/rollout-analysis-template.example.yml').read_text())
    fixture = yaml.safe_load((ROOT / 'monitoring/prometheus/rollout-analysis.test.yml').read_text())
    expected = [m['provider']['prometheus']['query'].replace('{{args.namespace}}', 'cf-fixture').replace('{{args.revision}}', 'new') for m in template['spec']['metrics']]
    assert len(fixture['tests']) == 7
    for case in fixture['tests']:
        assert [check['expr'] for check in case['promql_expr_test']] == expected
