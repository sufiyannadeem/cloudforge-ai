"""Real API/middleware tests: deterministic references, never provider inference."""
import asyncio
from types import SimpleNamespace
import httpx2 as httpx
import pytest
from . import analysis_routes
from .main import app
from .rag import OperationalKnowledgeBase
from .test_telemetry_api import KEY, signed_request


@pytest.mark.parametrize('role,status', [('developer',403),('sre',200),('platform-engineer',200)])
def test_knowledge_role_boundary_without_inference(monkeypatch,tmp_path,role,status):
    monkeypatch.setenv('CLOUDFORGE_FRONTEND_KEY',KEY)
    (tmp_path/'rollouts.md').write_text('# Deployment recovery\n\nDeploymentServiceHighLatency deployment-service rollout evidence and rollback.')
    import hashlib, json
    from . import project_evidence
    from fastapi import HTTPException
    def authorize(incident, claims):
        if incident != 'owned': raise HTTPException(404,'Unknown ownership')
        return '00000000-0000-0000-0000-000000000001'
    monkeypatch.setattr(project_evidence,'authorize_incident',authorize)
    (tmp_path/'manifest.json').write_text(json.dumps({'schema_version':2,'documents':{
        'rollouts.md':{'sha256':hashlib.sha256((tmp_path/'rollouts.md').read_bytes()).hexdigest(),
                       'reviewed_by':'offline-review','projects':['00000000-0000-0000-0000-000000000001'],'signals':['latency']},
        # Foreign file is absent: scope must filter it before reading content.
        'private.md':{'sha256':'0'*64,'reviewed_by':'offline-review',
                      'projects':['00000000-0000-0000-0000-000000000002'],'signals':['latency']}}}))
    monkeypatch.setenv('AI_KNOWLEDGE_DIR',str(tmp_path))
    reads=[]
    def get(incident_id):
        reads.append(incident_id)
        return SimpleNamespace(service='deployment-service',alert_name='DeploymentServiceHighLatency') if incident_id=='owned' else None
    monkeypatch.setattr(analysis_routes.incident_store,'get',get)
    async def request(incident):
        path=f'/api/v1/incidents/{incident}/knowledge'
        signed=signed_request(path,role=role)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            return await asyncio.wait_for(client.get(path,headers=dict(signed.headers)),timeout=3)
    result=asyncio.run(request('owned'))
    assert result.status_code==status
    if status==200:
        data=result.json()
        assert data['authoritative'] is False and data['incident_id']=='owned'
        assert [r['path'] for r in data['references']]==['rollouts.md']
        assert 'private, no-store'==result.headers['cache-control']
        assert asyncio.run(request('missing')).status_code==404
    else:
        assert reads==[]
