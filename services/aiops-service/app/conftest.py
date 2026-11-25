"""Bounded in-process API fixtures: no sockets and no worker-thread scheduling.

ASGITransport does not implement HTTP timeout enforcement. Sync route dependencies
are isolated inline in these offline tests; all their I/O must be explicit fixtures.
Production scheduling is untouched. Async requests also use asyncio.wait_for.
"""
import pytest


@pytest.fixture(autouse=True)
def bounded_api_environment(request,monkeypatch):
    if request.node.path.name not in {'test_ai_enrichment_api.py','test_knowledge_api.py','test_secure_integration.py','test_remediation_route_auth.py','test_remediation_reviews.py','test_trusted_telemetry.py'}:
        return
    import fastapi.routing
    import fastapi.dependencies.utils
    import starlette.routing
    import starlette.concurrency
    from . import main
    import socket
    async def inline(func,*args,**kwargs):
        return func(*args,**kwargs)
    def no_network(*args,**kwargs):
        raise AssertionError('Unmocked network access in offline API test')
    monkeypatch.setattr(fastapi.routing,'run_in_threadpool',inline)
    monkeypatch.setattr(fastapi.dependencies.utils,'run_in_threadpool',inline)
    monkeypatch.setattr(starlette.routing,'run_in_threadpool',inline)
    monkeypatch.setattr(starlette.concurrency,'run_in_threadpool',inline)
    monkeypatch.setattr(main,'run_in_threadpool',inline)
    monkeypatch.setattr(socket,'create_connection',no_network)
    monkeypatch.setenv('AI_PROVIDER','disabled')
    # Dedicated worker configuration only for in-process worker tests.
    monkeypatch.setenv('AWS_ROLE_ARN','arn:aws:iam::123456789012:role/offline-inference')
    monkeypatch.setenv('AWS_WEB_IDENTITY_TOKEN_FILE','/offline/never-read')
    monkeypatch.setenv('AWS_EC2_METADATA_DISABLED','true')
