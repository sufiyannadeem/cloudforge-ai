"""Offline source-policy/negative-control checks; never calls AWS or Terraform apply."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / 'infrastructure/terraform/environments/dev'
TARGETS = {'AVD-AWS-0052', 'AVD-AWS-0054', 'AVD-AWS-0104', 'AVD-AWS-0040', 'AVD-AWS-0041'}


def scan(folder, tmp_path):
    if not shutil.which('trivy'):
        pytest.fail('Trivy is required for private Terraform security regressions')
    output = tmp_path / 'scan.json'
    p = subprocess.run(['trivy', 'config', '--skip-check-update', '--severity', 'HIGH,CRITICAL',
                        '--ignorefile', str(ROOT/'.trivyignore'), '--format', 'json',
                        '--output', str(output), str(folder)], capture_output=True, text=True, timeout=90)
    assert p.returncode == 0, p.stderr[-2000:]
    report = json.loads(output.read_text())
    return [finding for result in report.get('Results', []) for finding in result.get('Misconfigurations', [])]


def copy_dev(tmp_path):
    folder = tmp_path/'dev';folder.mkdir()
    for p in DEV.glob('*.tf'):shutil.copyfile(p, folder/p.name)
    return folder


def resource(text, kind, name):
    # Resource bounds suffice for these named, top-level HCL blocks.
    start = text.index(f'resource "{kind}" "{name}" {{')
    following = re.search(r'^resource ', text[start+1:], re.M)
    return text[start:start+1+following.start()] if following else text[start:]


def test_private_transport_exception_requires_the_guarded_topology():
    api = (DEV/'api_gateway.tf').read_text();eks = (DEV/'eks.tf').read_text()
    alb = resource(api,'aws_lb','internal');listener = resource(api,'aws_lb_listener','internal_http')
    assert re.search(r'\binternal\s*=\s*true\b', alb)
    assert re.search(r'\bdrop_invalid_header_fields\s*=\s*true\b', alb)
    assert 'module.vpc.private_subnets' in alb
    assert re.search(r'load_balancer_arn\s*=\s*aws_lb.internal.arn', listener)
    assert re.search(r'port\s*=\s*80\b', listener) and '"HTTP"' in listener
    assert re.search(r'integration_uri\s*=\s*aws_lb_listener.internal_http.arn', api)
    assert re.search(r'connection_type\s*=\s*"VPC_LINK"', api)
    alb_sg = resource(api,'aws_security_group','internal_alb')
    assert 'security_groups = [aws_security_group.vpc_link.id]' in alb_sg
    assert 'cidr_blocks = module.vpc.private_subnets_cidr_blocks' in alb_sg
    assert '0.0.0.0/0' not in alb_sg and '::/0' not in alb_sg
    assert api.count('#trivy:ignore:AVD-AWS-0054:exp:2026-12-22') == 1
    assert not re.search(r'^\s*(?:AVD-)?AWS-00(?:40|41|52|54)\s*$', (ROOT/'.trivyignore').read_text(), re.M)
    assert re.search(r'endpoint_private_access\s*=\s*true', eks)
    assert re.search(r'endpoint_public_access\s*=\s*false', eks)
    assert 'referenced_security_group_id = var.eks_operator_security_group_id' in eks
    for name in ('efs', 'rds'):
        assert re.search(r'\begress\s*=\s*\[\]', resource((DEV/f'{name}.tf').read_text(),'aws_security_group',name))


def test_dev_has_no_high_or_critical_findings(tmp_path):
    assert not scan(copy_dev(tmp_path), tmp_path)


def test_removing_only_private_http_exception_restores_aws0054(tmp_path):
    folder = copy_dev(tmp_path);file = folder/'api_gateway.tf'
    file.write_text(file.read_text().replace('#trivy:ignore:AVD-AWS-0054:exp:2026-12-22',''))
    findings = scan(folder, tmp_path)
    assert 'AVD-AWS-0054' in {'AVD-' + f['ID'].removeprefix('AVD-') for f in findings}


def test_unrelated_unsafe_resources_still_trigger_all_five_checks(tmp_path):
    folder = copy_dev(tmp_path)
    (folder/'unsafe-negative-control.tf').write_text('''
resource "aws_lb" "unsafe" {
  internal = false
  load_balancer_type = "application"
  drop_invalid_header_fields = false
}
resource "aws_lb_listener" "unsafe_http" {
  load_balancer_arn = aws_lb.unsafe.arn
  port = 80
  protocol = "HTTP"
  default_action {
    type = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}
resource "aws_security_group" "unsafe_egress" {
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_eks_cluster" "unsafe_public" {
  vpc_config {
    endpoint_public_access = true
    endpoint_private_access = true
    public_access_cidrs = ["0.0.0.0/0"]
    subnet_ids = ["subnet-00000000000000000"]
  }
}
''')
    findings = scan(folder, tmp_path)
    assert TARGETS <= {'AVD-' + f['ID'].removeprefix('AVD-') for f in findings}
