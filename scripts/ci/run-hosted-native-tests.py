#!/usr/bin/env python3
"""Require real Terraform schema and TLS cases; never turn skipped tests into success."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
if not os.getenv('TF_OFFLINE_PROVIDER_MIRROR'):raise SystemExit('Reviewed local provider mirror required')
env=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1');env.pop('PYTEST_ADDOPTS',None)
with tempfile.TemporaryDirectory(prefix='cloudforge-native-junit-') as folder:
    report=Path(folder)/'native.xml'
    subprocess.run([sys.executable,'-m','pytest','tests/test_monitoring_tls.py',
        'tests/test_ci_pipeline_hardening.py::test_terraform_validate_bootstrap_and_dev',
        '-q','--junitxml='+str(report)],cwd=ROOT,env=env,check=True,timeout=240)
    cases=list(ET.parse(report).getroot().iter('testsuite'))
    if (sum(int(s.get('tests','0')) for s in cases)!=7 or
        any(int(s.get(k,'0')) for s in cases for k in ('skipped','failures','errors'))):
        raise SystemExit('All seven real native/TLS tests must pass without skips or filtering')
