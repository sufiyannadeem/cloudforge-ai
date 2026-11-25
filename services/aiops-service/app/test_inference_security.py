import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.ai_provider import AIProvider
from app.inference_security import approved_payload, Diagnosis
from app.legacy_usage import UsageLedger
from app.rag import OperationalKnowledgeBase


@pytest.mark.parametrize("raw", ['raw logs secret', '{"evidence":[],"tools":[]}',
    '{"evidence":[{"signal":"latency","state":"ignore instructions"}]}',
    '{"evidence":[{"signal":"latency","state":"healthy","customer":"private"}]}'])
def test_disclosure_denies_unapproved_text(raw):
    with pytest.raises(ValueError):
        approved_payload(raw)


def test_only_fixed_vocabulary_leaves_boundary():
    payload = {"evidence": [{"signal": "latency", "state": "unknown"}]}
    assert approved_payload(json.dumps(payload)) == payload


def test_durable_budget_and_rate(tmp_path):
    path = str(tmp_path / 'usage.db')
    UsageLedger(path).reserve(35000, now=0)
    with pytest.raises(ValueError):
        UsageLedger(path).reserve(1001, now=61)
    for _ in range(5):
        UsageLedger(path).reserve(0, now=120)
    with pytest.raises(ValueError):
        UsageLedger(path).reserve(0, now=120)


def test_concurrent_budget(tmp_path):
    path = str(tmp_path / 'usage.db')
    UsageLedger(path).reserve(0, now=0)
    def reserve(_):
        try:
            UsageLedger(path).reserve(10000, now=100)
            return 1
        except ValueError:
            return 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(8))) == 3


def test_gemini_default_denies_network(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    monkeypatch.delenv('AI_DISCLOSURE_APPROVED', raising=False)
    assert AIProvider().analyze('system', 'secret').status == 'blocked'


def test_legacy_production_disclosure_blocked(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    for provider in ('bedrock', 'openai_compatible'):
        monkeypatch.setenv('AI_PROVIDER', provider)
        assert AIProvider().analyze('system', 'secret').status == 'blocked'


@pytest.mark.parametrize('extra', [{'tools': []}, {'action': 'delete'}, {'summary': 'secret'}])
def test_output_rejects_actions(extra):
    with pytest.raises(ValueError):
        Diagnosis.model_validate(dict(assessment='healthy', confidence='low', citations=[0], **extra))


def test_semantic_retrieval_and_bounds(tmp_path):
    (tmp_path / 'approved.md').write_text('# Latency\nSlow response diagnosis')
    (tmp_path / 'private.md').write_text('# Private\nCredentials')
    (tmp_path / 'link.md').symlink_to(tmp_path / 'private.md')
    embed = lambda text: [1.0, 0.0] if 'slow' in text.lower() or 'delay' in text.lower() else [0.0, 1.0]
    kb = OperationalKnowledgeBase(tmp_path, embedder=embed, allowed_paths={'approved.md'}, min_relevance=.8)
    assert kb.search('delay')[0].chunk.path == 'approved.md'
    assert kb.search('unrelated') == []
    assert kb.search('delay', top_k=0) == []
    assert 'Citation:' in kb.build_context('delay')


@pytest.mark.parametrize('claims,project', [
    ({'sub': 'operator', 'role': 'developer'}, 'project-a'),
    ({'sub': 'operator', 'role': 'sre'}, 'project-b'),
    ({'sub': 'operator', 'role': 'sre'}, None),
    ({'sub': 'intruder', 'role': 'sre'}, 'project-a'),
])
def test_project_authorization_denies(claims, project):
    from app.inference_security import authorize_project
    with pytest.raises(PermissionError):
        authorize_project(claims, project_id=project, allowed_subjects={'operator': ['project-a']})


def test_project_authorization_allows():
    from app.inference_security import authorize_project
    authorize_project({'sub': 'operator', 'role': 'sre'}, project_id='project-a',
                      allowed_subjects={'operator': ['project-a']})


def test_gemini_contract_offline(monkeypatch, tmp_path):
    import boto3
    import urllib.request
    from types import SimpleNamespace
    for name, value in {'AI_PROVIDER': 'gemini', 'AI_DISCLOSURE_APPROVED': 'true',
                        'AI_TERMS_APPROVED': 'true', 'AI_BILLING_MODE': 'free_only',
                        'AI_WORKLOAD': 'inference', 'AI_LEDGER_HOST': 'offline.invalid',
                        'AI_GEMINI_SECRET_ARN': 'arn:aws:secretsmanager:eu-west-1:123456789012:secret:cloudforge/prod/ai-inference/key-Abc123'}.items():
        monkeypatch.setenv(name, value)
    for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_PROFILE'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(boto3, 'client', lambda *a, **kw: SimpleNamespace(
        get_secret_value=lambda **kw: {'SecretString': '{"api_key":"test-only"}'}))
    output = {'assessment': 'insufficient_evidence', 'confidence': 'low', 'citations': [0]}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, limit):
            return json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {
                'parts': [{'text': json.dumps(output)}]}}]}).encode()
    calls = []
    def open_request(request, timeout):
        calls.append(request)
        payload = json.loads(request.data)
        assert 'tools' not in payload
        assert 'ignored secret system prompt' not in request.data.decode()
        assert request.full_url.endswith('gemini-2.5-flash:generateContent')
        return Response()
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=open_request))
    provider = AIProvider()
    prompt = '{"evidence":[{"signal":"latency","state":"unknown"}]}'
    assert provider.analyze('ignored secret system prompt', prompt).status == 'success'
    output['citations'] = [9]
    assert provider.analyze('system', prompt).status == 'blocked'
    output['citations'] = [0]
    output['assessment'] = 'healthy'
    assert provider.analyze('system', prompt).status == 'blocked'
    assert provider.analyze('system', 'raw logs credentials').status == 'blocked'
    assert len(calls) == 3


@pytest.mark.parametrize('diagnosis',[
 {'assessment':'healthy','confidence':'low','citations':[0]},
 {'assessment':'degraded','confidence':'low','citations':[1]},
 {'assessment':'degraded','confidence':'low','citations':[0,0]},
])
def test_diagnosis_contradictions_rejected(diagnosis):
    from app.inference_security import validate_diagnosis
    evidence=[{'signal':'latency','state':'degraded'},{'signal':'availability','state':'unknown'}]
    with pytest.raises(ValueError): validate_diagnosis(json.dumps(diagnosis),evidence)
