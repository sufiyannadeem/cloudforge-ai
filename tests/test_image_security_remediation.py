"""Keep the tested compiler/CLI aligned with the binaries shipped in images.

Actual vulnerability acceptance remains the fail-closed runtime image scan.
"""
from pathlib import Path
import re
import yaml

ROOT=Path(__file__).resolve().parents[1]


def test_go_builder_and_ci_module_toolchains_match():
    versions=[]
    for service in ['project-service','infrastructure-service','deployment-service']:
        folder=ROOT/'services'/service
        version=re.search(r'^go (\d+\.\d+\.\d+)$',(folder/'go.mod').read_text(),re.M).group(1)
        builder=re.search(r'^FROM golang:(\d+\.\d+\.\d+)-alpine@sha256:[0-9a-f]{64} AS builder$',(folder/'Dockerfile').read_text(),re.M)
        assert builder and builder.group(1)==version
        versions.append(version)
    identity=re.search(r'^go (\d+\.\d+\.\d+)$',(ROOT/'services/service-identity/go.mod').read_text(),re.M).group(1)
    assert set(versions)=={identity}
    ci=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    for name in ['project','infrastructure','deployment']:
        setup=next(s for s in ci['jobs'][name+'-service-ci']['steps'] if s.get('uses','').startswith('actions/setup-go@'))
        assert setup['with']['go-version-file']==f'services/{name}-service/go.mod'


def test_terraform_validation_matches_shipped_pinned_cli():
    dockerfile=(ROOT/'services/infrastructure-service/Dockerfile').read_text()
    release=re.search(r'^FROM hashicorp/terraform:(\d+\.\d+\.\d+)@sha256:[0-9a-f]{64} AS terraform$',dockerfile,re.M)
    assert release
    ci=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    setup=next(s for s in ci['jobs']['terraform-ci']['steps'] if s.get('uses','').startswith('hashicorp/setup-terraform@'))
    assert setup['with']['terraform_version']==release.group(1)
