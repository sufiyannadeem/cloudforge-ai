#!/usr/bin/env python3
"""Scaffold validated deployment inputs from Terraform outputs and verified release manifest.
Never accesses live AWS services, never requests or emits secret values or plaintext credentials.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

# Import renderer for dry-run validation
spec = importlib.util.spec_from_file_location('render_kubernetes', ROOT / 'scripts/render-kubernetes.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

SERVICES = [
    'project-service',
    'infrastructure-service',
    'deployment-service',
    'aiops-service',
    'finops-service',
    'frontend',
]

SECRET_SPECS = {
    'cloudforge-frontend-project': {'CLOUDFORGE_FRONTEND_PROJECT_KEY': 'CLOUDFORGE_FRONTEND_PROJECT_KEY'},
    'cloudforge-frontend-infrastructure': {'CLOUDFORGE_FRONTEND_INFRASTRUCTURE_KEY': 'CLOUDFORGE_FRONTEND_INFRASTRUCTURE_KEY'},
    'cloudforge-frontend-deployment': {'CLOUDFORGE_FRONTEND_DEPLOYMENT_KEY': 'CLOUDFORGE_FRONTEND_DEPLOYMENT_KEY'},
    'cloudforge-aiops-deployment': {'CLOUDFORGE_AIOPS_DEPLOYMENT_KEY': 'CLOUDFORGE_AIOPS_DEPLOYMENT_KEY'},
    'cloudforge-finops-audit-db': {'FINOPS_AUDIT_DATABASE_URL': 'FINOPS_AUDIT_DATABASE_URL'},
    'cloudforge-finops-project-db': {'FINOPS_PROJECT_DATABASE_URL': 'FINOPS_PROJECT_DATABASE_URL'},
    'cloudforge-frontend-finops': {'CLOUDFORGE_FRONTEND_FINOPS_KEY': 'CLOUDFORGE_FRONTEND_FINOPS_KEY'},
    'cloudforge-frontend-aiops': {'CLOUDFORGE_FRONTEND_AIOPS_KEY': 'CLOUDFORGE_FRONTEND_AIOPS_KEY'},
    'cloudforge-alertmanager-identity': {'CLOUDFORGE_ALERTMANAGER_KEY': 'CLOUDFORGE_ALERTMANAGER_KEY'},
    'cloudforge-frontend-credentials': {'CLOUDFORGE_SESSION_SECRET': 'CLOUDFORGE_SESSION_SECRET'},
    'cloudforge-project-db': {'DATABASE_URL': 'DATABASE_URL'},
    'cloudforge-infrastructure-db': {'DATABASE_URL': 'DATABASE_URL'},
    'cloudforge-deployment-db': {'DATABASE_URL': 'DATABASE_URL'},
    'cloudforge-aiops-db': {'DATABASE_URL': 'DATABASE_URL'},
    'cloudforge-migration-db': {'DATABASE_URL': 'DATABASE_URL'},
}


def unwrap_tf_value(val):
    if isinstance(val, dict) and 'value' in val:
        return val['value']
    return val


def scaffold(tf_outputs, images_manifest, env='dev', account_id=None, region=None,
             state_bucket=None, image_pull_secret=None, bindings=None):
    # Extract unwrap outputs
    clean_tf = {k: unwrap_tf_value(v) for k, v in tf_outputs.items()}

    # Deduce account_id if not explicitly provided
    if not account_id:
        oidc_arn = clean_tf.get('eks_oidc_provider_arn') or ''
        match = re.search(r'arn:aws:iam::([0-9]{12}):', oidc_arn)
        if match:
            account_id = match.group(1)
        else:
            secret_arn = clean_tf.get('rds_master_user_secret_arn') or ''
            match = re.search(r'arn:aws:secretsmanager:[a-z0-9-]+:([0-9]{12}):', secret_arn)
            if match:
                account_id = match.group(1)

    if not account_id or not re.fullmatch(r'[0-9]{12}', account_id):
        raise ValueError('Valid 12-digit AWS account_id required or must be present in Terraform outputs')

    # Deduce region if not explicitly provided
    if not region:
        secret_arn = clean_tf.get('rds_master_user_secret_arn') or ''
        match = re.search(r'arn:aws:secretsmanager:([a-z]{2}-[a-z]+-[0-9]):', secret_arn)
        if match:
            region = match.group(1)
        else:
            raise ValueError('Explicit region or a verified regional Terraform secret ARN is required')

    if not re.fullmatch(r'[a-z]{2}-[a-z]+-[0-9]', region):
        raise ValueError(f'Invalid AWS region: {region}')

    # Process images from manifest
    manifest_images = images_manifest.get('images', images_manifest)
    images = {}
    digest_regex = re.compile(r'[a-z0-9][a-z0-9.:/_-]*@sha256:[0-9a-f]{64}')
    for svc in SERVICES:
        img = manifest_images.get(svc)
        if not img or not isinstance(img, str) or not digest_regex.fullmatch(img):
            raise ValueError(f'Missing or invalid digest-pinned image for {svc}')
        images[svc] = img

    alb_subnets = clean_tf.get('internal_alb_subnet_cidrs')
    if not alb_subnets:
        raise ValueError('Terraform internal_alb_subnet_cidrs output required for ALB data-plane access')

    # No invented IAM identities, secret suffixes, state buckets or egress paths.
    if not isinstance(bindings, dict):
        raise ValueError('Reviewed bindings metadata is required; identities must not be inferred')
    roles = bindings['roles']
    provisioner_role = bindings.get('provisioner_role_arn', '')
    state_bucket = state_bucket or clean_tf.get('terraform_state_bucket_name') or bindings.get('state_bucket')
    if not state_bucket:
        raise ValueError('Verified bootstrap state bucket output/binding is required')
    secrets = bindings['secrets']
    egress_cidrs = bindings['egress_cidrs']

    config = {
        'account_id': account_id,
        'region': region,
        'images': images,
        'roles': roles,
        'provisioner_role_arn': provisioner_role,
        'state_bucket': state_bucket,
        'storage': {
            'class': 'efs-sc',
            'size': '10Gi',
        },
        'monitoring_namespace': 'monitoring',
        'monitoring_tls': {
            'prometheus_url': 'https://prometheus.monitoring.svc:9090',
            'prometheus_pod_port': 9090,
            'grafana_url': 'https://grafana.monitoring.svc:3000',
            'grafana_pod_port': 3000,
            'ca_configmap': 'cloudforge-monitoring-ca',
        },
        'public_origin': clean_tf.get('api_gateway_endpoint'),
        'alb_subnet_cidrs': alb_subnets,
        'ingress_namespace': 'kube-system',
        'ingress_app': 'aws-load-balancer-controller',
        'egress_cidrs': egress_cidrs,
        'ai': {
            'provider': 'disabled',
        },
        'secrets': secrets,
        'rollouts': {
            'enabled': False,
            'analysis_template': None,
        },
        'reliability': {
            'min_replicas': 2,
            'max_replicas': 4,
            'cpu_utilization': 70,
        },
        'database_ca_configmap': 'cloudforge-rds-ca',
        'drift': {
            'enabled': False,
        },
    }

    for key in ('free_plan', 'secret_delivery', 'preseeded_secret_keys', 'preview_rollout_mode'):
        if key in bindings:
            config[key] = bindings[key]

    if config.get('free_plan'):
        config['reliability']['max_replicas'] = 2

    if image_pull_secret:
        renderer.checked(r'[a-z0-9][a-z0-9.-]*', image_pull_secret, 'image_pull_secret')
        config['image_pull_secret'] = image_pull_secret

    # Validate end-to-end with the renderer
    renderer.render(config)

    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terraform-outputs', required=True, type=Path,
                        help='Path to JSON file containing terraform output -json')
    parser.add_argument('--bindings', required=True, type=Path, help='Reviewed non-secret identities, secret metadata and network bindings')
    parser.add_argument('--images', required=True, type=Path,
                        help='Path to JSON file containing verified release images manifest')
    parser.add_argument('--output', type=Path, default=None,
                        help='Path to write generated deployment-inputs.json (prints to stdout if omitted)')
    parser.add_argument('--environment', default='dev', help='Deployment environment (default: dev)')
    parser.add_argument('--account-id', default=None, help='AWS 12-digit Account ID')
    parser.add_argument('--region', default=None, help='AWS Region')
    parser.add_argument('--state-bucket', default=None, help='Terraform state bucket name')
    parser.add_argument('--image-pull-secret', default=None, help='Optional GHCR imagePullSecret name')

    args = parser.parse_args()

    tf_data = json.loads(args.terraform_outputs.read_text())
    img_data = json.loads(args.images.read_text())

    config = scaffold(
        tf_outputs=tf_data,
        images_manifest=img_data,
        env=args.environment,
        account_id=args.account_id,
        region=args.region,
        state_bucket=args.state_bucket,
        image_pull_secret=args.image_pull_secret,
        bindings=json.loads(args.bindings.read_text()),
    )

    print('REVIEW REQUIRED: metadata validation does not prove target existence; verify release signatures and run the Free-plan preflight before deployment.', file=sys.stderr)
    formatted = json.dumps(config, indent=2) + '\n'
    if args.output:
        args.output.write_text(formatted)
        print(f'Wrote validated deployment inputs to {args.output}')
    else:
        print(formatted, end='')


if __name__ == '__main__':
    main()
