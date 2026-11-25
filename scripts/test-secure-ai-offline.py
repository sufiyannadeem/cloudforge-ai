#!/usr/bin/env python3
"""Focused secure AI tests with all socket connections disabled. No external calls."""
import os
import socket
import sys
from pathlib import Path

root=Path(__file__).resolve().parent.parent
os.chdir(root)
sys.path.insert(0,str(root/'services/aiops-service'))
os.environ.pop('AI_TEST_POSTGRES_DSN',None)  # Real PostgreSQL tests are a separate opt-in gate.
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'


def offline(*args,**kwargs):
    raise OSError('Network disabled for offline verification')

socket.socket.connect=offline
socket.create_connection=offline
import pytest
files=['test_inference_security.py','test_secure_integration.py','test_postgres_inference.py',
       'test_ai_enrichment_api.py','test_production_rag.py','test_knowledge_api.py','test_rag.py','test_ai_guardrails.py',
       'test_ai_tools.py','test_ai_enrichment.py','test_ai_enrichment_failure_modes.py',
       'test_ai_enrichment_evidence_package.py','test_bedrock_provider.py','test_analysis_service.py',
       'test_database_security.py','test_trusted_telemetry.py','test_remediation_reviews.py','test_remediation.py','test_remediation_lifecycle.py','test_remediation_route_auth.py']
raise SystemExit(pytest.main([str(root/'services/aiops-service/app'/name) for name in files]+['-q']))
