"""Capacity regressions: no live AWS calls."""
import importlib.util
from preflight_fixtures import scenario_inputs
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('capacity',ROOT/'scripts/compare-preview-capacity.py')
capacity=importlib.util.module_from_spec(spec);spec.loader.exec_module(capacity)


def test_selected_profile_fits_but_rejects_surge_and_live_migration():
    result=capacity.compare(*scenario_inputs()); selected=result['options'][2]
    assert selected['scheduling_fit']
    assert selected['phases']['steady']['demand']=={'cpu_m':3710,'memory_mi':7336,'pods':32,'non_host_pods':26}
    assert not selected['phases']['single_surge_or_live_migration']['feasible']
    assert not selected['phases']['all_app_surge']['feasible']
    assert selected['derived_node_budget']=={'cpu_m':1930,'memory_mi':6627,'pods':35,'pod_ips':33}
    assert selected['five_day']['envelope_total']=='93.51'
    assert selected['five_day']['arithmetic_within_cap']
    assert result['deployment_verdict']=='NO-GO'
    assert not result['options'][0]['scheduling_fit']
    assert not result['options'][1]['scheduling_fit']


def test_full_ha_larger_nodes_exceed_cost_cap_despite_quota_fit():
    for option in capacity.compare(*scenario_inputs())['options'][5:]:
        assert option['scheduling_fit'] and option['quota_fits_input']
        assert not option['five_day']['arithmetic_within_cap']


def test_ip_exhaustion_blocks_placement_independently_of_cpu_memory():
    groups=[{'name':'app','cpu_m':1,'memory_mi':1,'replicas':2,'spread':True}]
    node={'cpu_m':100,'memory_mi':100,'pods':10,'pod_ips':0}
    assert not capacity.scheduler.placement(groups,node)['feasible']
    groups[0]['host_network']=True
    assert capacity.scheduler.placement(groups,node)['feasible']


def test_selected_addon_schema_and_binding_fail_closed():
    import hashlib
    import json
    import jsonschema
    bundle=ROOT/'deploy/preview'
    cfg=json.loads((ROOT/'deploy/controllers/config/aws-efs-csi-driver-configuration.json').read_text())
    schema=json.loads((ROOT/'deploy/controllers/schemas/aws-efs-csi-driver-schema.json').read_text())
    jsonschema.validators.validator_for(schema)(schema).validate(cfg)
    assert cfg['controller']['replicaCount']==1
    profile=json.loads((bundle/'scheduling-profile.json').read_text())
    assert next(g for g in profile['system'] if g['name']=='efs-csi-controller')['replicas']==cfg['controller']['replicaCount']
    import pytest
    renderer=capacity.module('renderer','render-kubernetes.py')
    with pytest.raises((TypeError,ValueError)):
        renderer.render(json.loads((bundle/'deployment-bindings.template.json').read_text()))
    assert not capacity.compare(*scenario_inputs())['selective_medium_one_efs_controller_without_grafana']['feasible']


def test_absent_or_stale_external_inputs_never_use_bundled_prices():
    import pytest
    from datetime import timedelta
    assert capacity.compare()['deployment_verdict']=='NO-GO'
    assert capacity.compare()['options']==[]
    catalog,evidence,now=scenario_inputs()
    with pytest.raises(ValueError,match='Stale'):
        capacity.compare(catalog,evidence,now+timedelta(days=2))
    result=capacity.compare(catalog,evidence,now)
    assert result['input_kind']=='SYNTHETIC_TEST_ONLY' and result['deployment_verdict']=='NO-GO'
