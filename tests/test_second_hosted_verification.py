"""Regressions for the confirmed second hosted verification failures."""
import copy
from pathlib import Path
import runpy

import jsonschema
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]


def acquisition():
    return runpy.run_path(str(ROOT/'scripts/ci/acquire-integration-inputs.py'))


def test_revised_lock_cannot_reuse_previous_hash_approval(monkeypatch):
    import hashlib
    module=acquisition()
    path=ROOT/'ci/integration-acquisition.json'
    previous='229740c6df87058f6c06162b908b8f48a9b408a5979ab6b5079492e0669e2d45'
    monkeypatch.setenv('CI_ACQUISITION_LOCK_SHA256',previous)
    monkeypatch.setenv('CI_ACQUISITION_APPROVED','true')  # Unit-only injected decision.
    with pytest.raises(ValueError,match='differs from environment-approved digest'):
        module['load'](path)
    monkeypatch.setenv('CI_ACQUISITION_LOCK_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.delenv('CI_ACQUISITION_APPROVED')
    with pytest.raises(ValueError,match='human acquisition approval is still pending'):
        module['load'](path)


@pytest.mark.parametrize('shape', [
    {'type':'string','format':'int-or-string'},
    {'x-kubernetes-int-or-string':True},
    {'x-kubernetes-int-or-string':True,'anyOf':[{'type':'integer'},{'type':'string'}]},
])
def test_int_or_string_referenced_definition_preserves_strict_objects(shape):
    module=acquisition()
    original=copy.deepcopy(shape)
    schema=module['standalone']({'type':'object','properties':{
        'port':{'$ref':'#/definitions/IntOrString'}},'required':['port']}, {'IntOrString':shape})
    jsonschema.Draft7Validator.check_schema(schema)
    validator=jsonschema.Draft7Validator(schema)
    for port in (80,8090,'http','50%'):
        validator.validate({'port':port})
    for port in (True,False,1.5,[],{},None):
        assert not validator.is_valid({'port':port})
    assert not validator.is_valid({'port':8090,'unexpected':True})
    assert not validator.is_valid({})
    assert shape==original


def test_crd_int_or_string_keeps_existing_branch_constraints():
    module=acquisition()
    schema=module['strict_schema']({'x-kubernetes-int-or-string':True,'anyOf':[
        {'type':'integer','minimum':1},{'type':'string','pattern':'^[a-z]+$'}]})
    validator=jsonschema.Draft7Validator(schema)
    for value in (1,80,'http'):
        validator.validate(value)
    for value in (0,-1,'8090',True,{},[],1.5,None):
        assert not validator.is_valid(value)


def test_slo_fixture_uses_actual_rules_without_changing_expected_values(tmp_path):
    prepare=runpy.run_path(str(ROOT/'monitoring/prometheus/test-slo-evidence.py'))['prepare_fixture']
    prepare(tmp_path)
    fixture=ROOT/'monitoring/prometheus/slo-evidence.test.yml'
    assert (tmp_path/fixture.name).read_bytes()==fixture.read_bytes()
    source=yaml.safe_load((ROOT/'monitoring/prometheus/rules/cloudforge-recording.yml').read_text())
    original={r['record']:r for g in source['groups'] for r in g['rules'] if r.get('record') in {
        'cloudforge:slo_availability:7d','cloudforge:slo_request_success:7d','cloudforge:slo_latency_compliance:7d'}}
    prepared=yaml.safe_load((tmp_path/'slo-evidence-rules.yml').read_text())
    assert prepared['groups'][0]['interval']=='15s'
    assert len(prepared['groups'][0]['rules'])==3
    for rule in prepared['groups'][0]['rules']:
        expected=copy.deepcopy(original[rule['record'].replace(':5m',':7d')])
        expected['record']=expected['record'].replace(':7d',':5m')
        expected['expr']=expected['expr'].replace('[7d]','[5m]').replace('>= 36288','>= 18')
        assert rule==expected
        assert '<= 45' in rule['expr']


def test_native_promtool_runs_generated_slo_fixture_in_its_directory(monkeypatch):
    native=runpy.run_path(str(ROOT/'scripts/verify-consolidated-release.py'))['native']
    monkeypatch.setenv('PROMTOOL','/cached/promtool')
    monkeypatch.setenv('KUBECONFORM','/cached/kubeconform')
    monkeypatch.setenv('KUBERNETES_SCHEMA_LOCATION','/cached/schemas')
    seen=[]
    def fake_run(command,cwd=ROOT,**kwargs):
        command=[str(arg) for arg in command]
        if command[:2]==['helm','template']:
            return 'kind: Deployment\nmetadata: {name: controller}\n'
        if command[:2]==['kubectl','kustomize']:
            return yaml.safe_dump({'kind':'Deployment','metadata':{'name':'aiops-service'},'spec':{
                'template':{'spec':{'containers':[{'name':'aiops-service','env':[{'name':'AI_PROVIDER','value':'gemini'}]}]}}}})
        if command[:3]==['/cached/promtool','test','rules']:
            directory=Path(cwd);fixture=yaml.safe_load((directory/command[3]).read_text())
            for pattern in fixture['rule_files']:
                assert list(directory.glob(pattern)), (directory,pattern)
            if command[3]=='slo-evidence.test.yml':
                assert directory!=ROOT/'monitoring/prometheus'
                assert (directory/'slo-evidence-rules.yml').is_file()
            seen.append(command[3])
        return ''
    monkeypatch.setitem(native.__globals__,'run',fake_run)
    rows=native()
    assert all(row['status']=='PASS' for row in rows)
    assert set(seen)=={p.name for p in (ROOT/'monitoring/prometheus').rglob('*.test.yml')}
