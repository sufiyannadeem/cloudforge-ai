#!/usr/bin/env python3
"""Fail if a verification runner has ambient production/provider credentials."""
import os
import subprocess
from pathlib import Path

if os.getenv('GITHUB_ACTIONS')!='true':raise SystemExit('CI-only verification guard')
forbidden=('DATABASE_URL','AI_API_KEY','AI_GEMINI_SECRET_ARN','GOOGLE_APPLICATION_CREDENTIALS',
           'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','AWS_PROFILE',
           'AWS_ROLE_ARN','AWS_WEB_IDENTITY_TOKEN_FILE','AWS_CONTAINER_CREDENTIALS_FULL_URI',
           'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI','KUBECONFIG')
if any(os.getenv(key) for key in forbidden) or any(k.startswith('TF_TOKEN_') and v for k,v in os.environ.items()):
    raise SystemExit('Verification requires a clean runner without application/cloud credentials')
print('No application/cloud credentials supplied; only scoped synthetic test inputs allowed')

root=Path(__file__).resolve().parents[2]
if subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=os.environ['GITHUB_SHA']:
    raise SystemExit('Checked-out source must exactly match the workflow event SHA')
