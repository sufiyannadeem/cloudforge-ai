from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from botocore.exceptions import ClientError
from fastapi import HTTPException
import pytest
from . import project_costs as attribution
from .identity_test_helpers import SignedTestClient
from .main import app

PROJECT='11111111-1111-4111-8111-111111111111'
FOREIGN='99999999-9999-4999-8999-999999999999'
RESOURCE='22222222-2222-4222-8222-222222222222'
INSTANCE='i-0123456789abcdef0'
ACCOUNT='123456789012'
REAL_PROJECT_RESOURCES=attribution.project_resources

@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setenv('CLOUDFORGE_FRONTEND_KEY','fixture-only-project-finops-frontend-key-32-bytes')
    monkeypatch.setenv('FINOPS_PROJECT_DATABASE_URL','fixture-project-read-only')
    monkeypatch.setenv('CLOUDFORGE_AWS_BILLING_ENABLED','true')
    now=datetime.now(UTC)
    row=dict(project_id=PROJECT,resource_id=RESOURCE,environment='preview',region='eu-west-1',account_id=ACCOUNT,instance_id=INSTANCE,verified_at=now-timedelta(days=30))
    reads=[]
    def scoped(dsn,project,claims):
        reads.append(claims)
        assert dsn=='fixture-project-read-only'
        if str(project)!=PROJECT:raise HTTPException(404,'Project not found')
        return [row]
    monkeypatch.setattr(attribution,'project_resources',scoped)
    days=[{'resource_id':RESOURCE,'date':(now.date()-timedelta(days=8-i)).isoformat(),'amount':'50' if i==7 else '1'} for i in range(8)]
    billing=Mock(return_value=([{'status':'actual','currency':'USD','amount':'57','resource_history':days}],{INSTANCE}))
    monkeypatch.setattr(attribution,'costs_for_region',billing)
    ec2=Mock()
    ec2.describe_instances.return_value={'Reservations':[{'OwnerId':ACCOUNT,'Instances':[{'InstanceId':INSTANCE,'InstanceType':'m6a.large','State':{'Name':'running'},'Tags':[{'Key':k,'Value':v} for k,v in attribution.expected_tags(row).items()]}]}]}
    monkeypatch.setattr(attribution.boto3,'client',lambda service,**_:ec2 if service=='ec2' else pytest.fail('Unscoped AWS service'))
    metric=Mock(return_value=dict(instance_id=INSTANCE,utilization_available=True,cpu_utilization_percent=5.0,datapoints_count=24))
    client=SimpleNamespace(get_account_id=lambda:ACCOUNT,get_ec2_cpu_utilization=metric)
    factory=Mock(return_value=client)
    monkeypatch.setattr(attribution,'AWSFinOpsClient',factory)
    return SimpleNamespace(row=row,days=days,billing=billing,ec2=ec2,metric=metric,client=client,factory=factory,reads=reads,api=SignedTestClient(app))

def get(fixture,kind='anomalies',role='developer',project=PROJECT,query=''):
    return fixture.api.get(f'/api/v1/finops/projects/{project}/{kind}{query}',headers={'X-Test-Human-Role':role,'X-CloudForge-Role':'platform-engineer'})

@pytest.mark.parametrize('role',['developer','sre','platform-engineer'])
@pytest.mark.parametrize('kind',['anomalies','optimizations'])
def test_signed_roles_and_unknown_project_denial(fixture,role,kind):
    url=f'/api/v1/finops/projects/{PROJECT}/{kind}'
    assert fixture.api.get(url).status_code==401 and fixture.reads==[]
    assert get(fixture,kind,role,FOREIGN).status_code==404
    fixture.billing.assert_not_called();fixture.factory.assert_not_called()
    response=get(fixture,kind,role)
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    assert fixture.reads[-1]['role']==role and response.json()['project_id']==PROJECT
    assert response.json()['advisory_only'] is True
    assert get(fixture,kind,role,query='?account_id=forged').status_code==400
    assert fixture.api.post(url,headers={'X-Test-Human-Role':role},json={'cpu':0,'savings':999}).status_code==405

def test_anomaly_uses_existing_engine_and_attributed_resource(fixture):
    data=get(fixture).json();row=data['resources'][0]
    assert data['status']=='available' and row['resource_id']==RESOURCE and row['sample_count']==8
    assert row['anomalies'][0]['severity']=='critical' and row['anomalies'][0]['evidence_quality']=='actual'
    assert fixture.billing.call_args.args[0][0]['project_id']==PROJECT
    assert fixture.billing.call_args.kwargs=={'window_days':14}

@pytest.mark.parametrize('mode',['missing','gap','mixed_currency','stale','foreign_billing'])
def test_incomparable_billing_is_unavailable_not_healthy(fixture,mode):
    if mode=='missing':fixture.billing.return_value=([],set())
    elif mode=='gap':fixture.days.pop(2)
    elif mode=='stale':
        for day in fixture.days:day['date']=(datetime.fromisoformat(day['date'])-timedelta(days=2)).date().isoformat()
    elif mode=='foreign_billing':fixture.days[0]['resource_id']=FOREIGN
    else:fixture.billing.return_value=([{'status':'actual','currency':'USD','amount':'4','resource_history':fixture.days[:4]},{'status':'actual','currency':'EUR','amount':'53','resource_history':fixture.days[4:]}],{INSTANCE})
    data=get(fixture).json()
    assert data['status']=='unavailable' and data['resources'][0]['anomalies']==[]

def test_estimated_baseline_is_labelled(fixture):
    fixture.billing.return_value=([{'status':'estimated','currency':'USD','amount':'57','resource_history':fixture.days}],{INSTANCE})
    row=get(fixture).json()['resources'][0]
    assert row['billing_quality']=='estimated' and row['anomalies'][0]['evidence_quality']=='estimated'

def test_verified_optimization_is_advisory_with_null_savings(fixture):
    data=get(fixture,'optimizations').json();row=data['resources'][0];item=row['recommendations'][0]
    assert data['approval_required'] is True and data['total_potential_monthly_savings_usd'] is None
    assert row['resource_id']==RESOURCE and row['telemetry_quality']=='actual'
    assert item['resource_id']==RESOURCE and item['action']=='HUMAN_APPROVAL_REQUIRED'
    assert item['potential_monthly_savings_usd'] is None and item['savings']['monthly_usd'] is None
    assert item['savings']['evidence_available'] is False and item['evidence']['instance_type']=='m6a.large'
    assert fixture.ec2.describe_instances.call_args.kwargs=={'InstanceIds':[INSTANCE]}
    assert fixture.metric.call_args.kwargs['instance_id']==INSTANCE

@pytest.mark.parametrize('mode',['wrong_account','bad_tag','missing_metrics','sparse_metrics','nan','missing_type','future','denied'])
def test_optimization_evidence_fails_closed(fixture,mode):
    if mode=='wrong_account':fixture.client.get_account_id=lambda:'000000000000'
    elif mode=='bad_tag':fixture.ec2.describe_instances.return_value['Reservations'][0]['Instances'][0]['Tags']=[]
    elif mode=='missing_type':fixture.ec2.describe_instances.return_value['Reservations'][0]['Instances'][0].pop('InstanceType')
    elif mode=='future':fixture.row['verified_at']=datetime.now(UTC)+timedelta(days=1)
    elif mode=='denied':fixture.metric.side_effect=ClientError({'Error':{'Code':'AccessDenied','Message':'fixture'}},'GetMetricStatistics')
    else:
        fixture.metric.return_value['utilization_available']=mode!='missing_metrics'
        if mode=='sparse_metrics':fixture.metric.return_value['datapoints_count']=1
        if mode=='nan':fixture.metric.return_value['cpu_utilization_percent']=float('nan')
    data=get(fixture,'optimizations').json()
    assert data['status']=='unavailable' and data['resources'][0]['recommendations']==[]
    if mode in {'wrong_account','bad_tag','future'}:fixture.metric.assert_not_called()

def test_no_billing_never_invents_savings(fixture):
    fixture.billing.side_effect=attribution.AWSFinOpsError('fixture missing billing')
    row=get(fixture,'optimizations').json()['resources'][0]
    assert row['status']=='available' and row['billing_quality']=='unavailable'
    assert row['billing_history']==[] and row['recommendations'][0]['potential_monthly_savings_usd'] is None

def test_disabled_preview_and_foreign_join_never_reach_aws(fixture,monkeypatch):
    monkeypatch.setenv('CLOUDFORGE_AWS_BILLING_ENABLED','false')
    assert get(fixture).status_code==503
    fixture.billing.assert_not_called()
    monkeypatch.setenv('CLOUDFORGE_AWS_BILLING_ENABLED','true');fixture.row['project_id']=FOREIGN
    assert get(fixture).status_code==503
    fixture.factory.assert_not_called()


@pytest.mark.parametrize('role,expected', [('developer',404),('sre',200),('platform-engineer',200)])
def test_real_membership_query_enforces_developer_isolation_and_operator_scope(fixture,monkeypatch,role,expected):
    # FOREIGN exists but belongs to another tenant. Exercise the actual shared
    # membership query, not just the endpoint's mocked attribution boundary.
    statements=[]
    foreign_row={**fixture.row,'project_id':FOREIGN}
    def execute(sql, params=None):
        statements.append((sql,params))
        if 'SELECT 1 FROM projects p' in sql:
            assert str(params[0])==FOREIGN and params[2]=='test-operator'
            return SimpleNamespace(fetchone=lambda:(1,) if params[1] else None)
        if 'FROM infrastructure_resources r' in sql:
            assert str(params[0])==FOREIGN
            return SimpleNamespace(fetchall=lambda:[foreign_row])
        assert 'READ ONLY' in sql
        return SimpleNamespace()
    db=Mock();db.__enter__=Mock(return_value=SimpleNamespace(execute=execute));db.__exit__=Mock(return_value=False)
    monkeypatch.setattr(attribution.psycopg,'connect',lambda *_args,**_kwargs:db)
    monkeypatch.setattr(attribution,'project_resources',REAL_PROJECT_RESOURCES)
    response=get(fixture,project=FOREIGN,role=role)
    assert response.status_code==expected
    assert statements[1][1][1] is (role!='developer')
    if expected==404:
        assert len(statements)==2
        fixture.billing.assert_not_called();fixture.factory.assert_not_called()
    else:
        assert response.json()['project_id']==FOREIGN
        assert fixture.billing.call_args.args[0][0]['project_id']==FOREIGN


def test_one_supported_currency_does_not_hide_incomplete_currency(fixture):
    fixture.billing.return_value=([{'status':'actual','currency':'USD','amount':'57','resource_history':fixture.days},
                                  {'status':'actual','currency':'EUR','amount':'1','resource_history':fixture.days[:1]}],{INSTANCE})
    data=get(fixture).json()
    assert data['status']=='partial' and data['resources'][0]['status']=='partial'
    assert len(data['resources'][0]['anomalies'])==1
