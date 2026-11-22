"""Synthetic arithmetic/schema inputs, never AWS observations or release evidence."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TIME = datetime(2030, 1, 1, tzinfo=timezone.utc)


def make_evidence():
    resources = []
    hashes = {}
    for folder in ('infrastructure/terraform/bootstrap', 'infrastructure/terraform/environments/dev'):
        for file in sorted((ROOT / folder).glob('*.tf')):
            path = str(file.relative_to(ROOT))
            hashes[path] = hashlib.sha256(file.read_bytes()).hexdigest()
            resources += [dict(source=path, type=kind, name=name) for kind, name in re.findall(
                r'resource\s+"(aws_[a-z0-9_]+)"\s+"([a-z0-9_]+)"', file.read_text())]
    rates = dict(eks_hour='0.10', node_hour='0.0456', rds_hour='0.035', nat_hour='0.048',
                 ipv4_hour='0.005', alb_hour='0.0252', endpoint_az_hour='0.011',
                 gp3_gb_month='0.088', rds_gp3_gb_month='0.127', efs_gb_month='0.33',
                 kms_key_month='1', secret_month='0.4', rds_surplus_vcpu_hour='0.075')
    return {'fixture_only': True, 'fixture_description': 'Invented test scenario; numeric rates are illustrative, not current quotes',
            'checked_at': FIXTURE_TIME.isoformat(), 'requested_days': 5,
            'checks': {
                'plan': {'status': 'VERIFIED_READ', 'data': {
                    'accountPlanType': 'FREE', 'accountPlanStatus': 'ACTIVE',
                    'accountPlanRemainingCredits': {'unit': 'USD', 'amount': '134.89'},
                    'accountPlanExpirationDate': (FIXTURE_TIME + timedelta(days=365)).isoformat()}},
                'quota_ec2_applied': {'status': 'VERIFIED_READ', 'data': {
                    'Quotas': [{'QuotaCode': 'L-1216C47A', 'Value': 8}]}},
                'instances': {'status': 'VERIFIED_READ', 'data': {'Reservations': []}},
                'instance_offerings': {'status': 'VERIFIED_READ', 'data': {
                    'InstanceTypeOfferings': [{'InstanceType': 't3.medium', 'Location': 'fixture-zone-a'}]}}},
            'inventory': {'source_sha256': hashes, 'resources': resources},
            'cost_model': {'usd_rates': rates, 'variable_allowance': '15', 'cleanup_allowance': '8',
                           'profile': 'SYNTHETIC arithmetic only'},
            'gates': {name: {'status': 'UNKNOWN', 'reason': 'Synthetic fixture has no real acceptance'} for name in (
                'service_feature_and_credit_coverage', 'regional_write_entitlements',
                'operator_role_and_restricted_access', 'controller_iam_and_pinned_images',
                'preseeded_secret_keys_and_database_bootstrap', 'private_egress_dns_and_policies',
                'node_capacity_and_standard_credit_load_test', 'fresh_signed_release',
                'bounded_usage_and_teardown_owner', 'account_wide_credit_burn_and_billing_lag')}}


def make_catalog():
    # These shapes/rates exercise model arithmetic. They are not registry/API snapshots.
    shapes = {'t3.large': (2, 8192, 3, 12, '.0912'), 't3a.large': (2, 8192, 3, 12, '.0816'),
              'm6a.large': (2, 8192, 3, 10, '.0963'), 't3.xlarge': (4, 16384, 4, 15, '.1824'),
              't3a.xlarge': (4, 16384, 4, 15, '.1632'), 'm6a.xlarge': (4, 16384, 4, 15, '.1926'),
              'c6a.xlarge': (4, 8192, 4, 15, '.1642')}
    checks = {}
    metadata = []
    offerings = []
    for name, (cpu, memory, enis, ips, rate) in shapes.items():
        metadata.append({'InstanceType': name, 'VCpuInfo': {'DefaultVCpus': cpu},
                         'MemoryInfo': {'SizeInMiB': memory},
                         'NetworkInfo': {'MaximumNetworkInterfaces': enis, 'Ipv4AddressesPerInterface': ips}})
        checks[name] = {'status': 'VERIFIED_READ', 'on_demand': [
            {'sku': 'SYNTHETIC-NOT-AWS', 'rate': {'unit': 'Hrs', 'pricePerUnit': {'USD': rate}}}]}
        offerings += [{'InstanceType': name, 'Location': 'fixture-zone-' + zone} for zone in ('a', 'b')]
    checks['instance_types'] = {'status': 'VERIFIED_READ', 'data': {'InstanceTypes': metadata}}
    checks['offered_azs'] = {'status': 'VERIFIED_READ', 'data': {'InstanceTypeOfferings': offerings}}
    return {'fixture_only': True, 'checked_at': FIXTURE_TIME.isoformat(), 'region': 'fixture-region', 'checks': checks}


def scenario_inputs():
    return make_catalog(), make_evidence(), FIXTURE_TIME
