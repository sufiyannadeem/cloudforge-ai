from pathlib import Path
import re
import yaml
ROOT=Path(__file__).resolve().parents[1]


def test_drift_workload_policy_has_no_mutation_or_role_escalation():
    text=(ROOT/'infrastructure/terraform/bootstrap/drift.tf').read_text()
    policy=text[text.index('resource "aws_iam_role_policy"'):]
    fields=re.findall(r'\bAction\s*=\s*(\[[^\]]*\]|"[^"]+")',policy,re.S)
    assert len(fields)==len(re.findall(r'\bAction\s*=',policy))
    actions=[action for field in fields for action in re.findall(r'"([^"]+)"',field)]
    assert actions and all(re.fullmatch(r'[a-z0-9]+:(Get|List|Describe)[A-Za-z]+',action) for action in actions)
    assert 'system:serviceaccount:cloudforge:cloudforge-drift' in text
    assert 'default = false' in text
    assert '/cloudforge/resources/*/terraform.tfstate' in text


def test_drift_alerts_are_loaded_and_never_synthesize_success():
    config=yaml.safe_load((ROOT/'monitoring/prometheus/prometheus.yml').read_text())
    assert '/etc/prometheus/rules/*.yml' in config['rule_files']
    rules=yaml.safe_load((ROOT/'monitoring/prometheus/rules/cloudforge-drift-alerts.yml').read_text())
    stale=rules['groups'][0]['rules'][1]['expr']
    assert 'kube_cronjob_created' in stale and 'unless' in stale
    assert 'or vector(0)' not in stale
    ksm=yaml.safe_load((ROOT/'deploy/kubernetes/kube-state-metrics-values.example.yml').read_text())
    assert {'jobs','cronjobs'} <= set(ksm['collectors'])
    assert 'kube_cronjob_created' in ksm['metricAllowlist']


def test_append_boundary_is_not_a_resource_or_approval_write_grant():
    sql=(ROOT/'deploy/postgres/002_runtime_grants.sql').read_text()
    body=sql[sql.index('CREATE OR REPLACE FUNCTION'):sql.index('REVOKE ALL ON FUNCTION')]
    assert 'SECURITY DEFINER SET search_path = pg_catalog' in body
    assert 'public.infrastructure_resources' in body and 'public.terraform_drift_scans' in body
    assert 'service:drift-scheduler' in body and 'pg_column_size' in body
    assert 'FOR UPDATE' in body and 'r.updated_at=p_revision' in body
    assert 'EXECUTE' not in body and 'GRANT UPDATE(updated_at)' not in sql
    assert 'SET LOCAL ROLE cf_migrator' in sql
    assert 'Table ACL revocation does not remove column ACLs' in sql
