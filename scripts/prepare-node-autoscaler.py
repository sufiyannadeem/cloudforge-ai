#!/usr/bin/env python3
"""Prepare review-only Cluster Autoscaler Helm values and IAM documents. No API calls."""
import argparse
import json
from pathlib import Path
import re
import runpy
import yaml

# Load the trusted sibling, independent of caller cwd/PYTHONPATH.
_review = runpy.run_path(str(Path(__file__).with_name('review_workspace.py')))
read_review_json = _review['read_review_json']
output_directory = _review['output_directory']




def checked(pattern, value, field):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('Invalid or missing ' + field)
    return value


def prepare(config):
    account = checked(r'[0-9]{12}', config['account_id'], 'account_id')
    region = checked(r'[a-z]{2}-[a-z]+-[0-9]', config['region'], 'region')
    cluster = checked(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', config['cluster_name'], 'cluster_name')
    minor = checked(r'1\.[0-9]{2}', config['cluster_minor'], 'cluster_minor')
    if int(minor.split('.')[1]) < 30:
        raise ValueError('Topology profile requires Kubernetes 1.30 or newer')
    checked(r'[0-9]+\.[0-9]+\.[0-9]+', config['chart_version'], 'reviewed chart_version')
    image = checked(r'[a-z0-9][a-z0-9.:/_-]*:v' + re.escape(minor) + r'\.[0-9]+@sha256:[0-9a-f]{64}', config['image'], 'minor-matched immutable image')
    repository, tag = image.rsplit(':v', 1)
    role = checked(rf'arn:aws:iam::{account}:role/[A-Za-z0-9+=,.@_/-]+', config['role_arn'], 'role_arn')
    oidc = checked(rf'arn:aws:iam::{account}:oidc-provider/oidc\.eks\.{region}\.amazonaws\.com/id/[A-Za-z0-9]+', config['oidc_provider_arn'], 'oidc_provider_arn')
    groups = config['asg_arns']
    if not isinstance(groups, list) or not groups:
        raise ValueError('Exact reviewed ASG ARNs are required')
    for arn in groups:
        checked(rf'arn:aws:autoscaling:{region}:{account}:autoScalingGroup:[a-fA-F0-9-]+:autoScalingGroupName/[A-Za-z0-9_.+=,@-]+', arn, 'asg_arn')
    service_account = 'cloudforge-node-autoscaler'
    selector = {'matchLabels': {'cloudforge.ai/component': 'node-autoscaler'}}
    values = {
        'cloudProvider': 'aws', 'awsRegion': region,
        'autoDiscovery': {'clusterName': cluster, 'tags': ['k8s.io/cluster-autoscaler/enabled', 'k8s.io/cluster-autoscaler/' + cluster]},
        'image': {'repository': repository, 'tag': 'v' + tag, 'pullPolicy': 'IfNotPresent'},
        'replicaCount': 2,
        'rbac': {'create': True, 'serviceAccount': {'create': True, 'name': service_account, 'annotations': {'eks.amazonaws.com/role-arn': role}}},
        'extraArgs': {'leader-elect': 'true', 'balance-similar-node-groups': 'true',
                      'skip-nodes-with-local-storage': 'true', 'skip-nodes-with-system-pods': 'true',
                      'scale-down-delay-after-add': '10m', 'scale-down-unneeded-time': '10m',
                      'max-graceful-termination-sec': '120'},
        'extraEnv': {'AWS_STS_REGIONAL_ENDPOINTS': 'regional'},
        'additionalLabels': selector['matchLabels'],
        'podDisruptionBudget': {'maxUnavailable': 1},
        'resources': {'requests': {'cpu': '100m', 'memory': '300Mi'}, 'limits': {'cpu': '1000m', 'memory': '1Gi'}},
        'securityContext': {'runAsNonRoot': True, 'runAsUser': 65534, 'runAsGroup': 65534, 'seccompProfile': {'type': 'RuntimeDefault'}},
        'containerSecurityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
        'updateStrategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxSurge': 1, 'maxUnavailable': 0}},
        'topologySpreadConstraints': [{'maxSkew': 1, 'minDomains': 2, 'topologyKey': key,
                                      'whenUnsatisfiable': 'DoNotSchedule', 'labelSelector': selector}
                                     for key in ['kubernetes.io/hostname', 'topology.kubernetes.io/zone']],
    }
    issuer = oidc.split('oidc-provider/', 1)[1]
    trust = {'Version': '2012-10-17', 'Statement': [{
        'Effect': 'Allow', 'Principal': {'Federated': oidc}, 'Action': 'sts:AssumeRoleWithWebIdentity',
        'Condition': {'StringEquals': {issuer + ':aud': 'sts.amazonaws.com', issuer + ':sub': 'system:serviceaccount:kube-system:' + service_account}},
    }]}
    policy = {'Version': '2012-10-17', 'Statement': [
        {'Sid': 'ApprovedNodeGroupsOnly', 'Effect': 'Allow',
         'Action': ['autoscaling:SetDesiredCapacity', 'autoscaling:TerminateInstanceInAutoScalingGroup'], 'Resource': groups,
         'Condition': {'StringEquals': {'aws:ResourceTag/k8s.io/cluster-autoscaler/enabled': 'true', 'aws:ResourceTag/k8s.io/cluster-autoscaler/' + cluster: 'owned'}}},
        {'Sid': 'RegionalInventory', 'Effect': 'Allow', 'Resource': '*',
         'Action': ['autoscaling:DescribeAutoScalingGroups', 'autoscaling:DescribeAutoScalingInstances',
                    'autoscaling:DescribeLaunchConfigurations', 'autoscaling:DescribeScalingActivities', 'autoscaling:DescribeTags',
                    'ec2:DescribeImages', 'ec2:DescribeInstanceTypes', 'ec2:DescribeLaunchTemplateVersions', 'ec2:GetInstanceTypesFromInstanceRequirements'],
         'Condition': {'StringEquals': {'aws:RequestedRegion': region}}},
        {'Sid': 'ClusterNodeGroupMetadata', 'Effect': 'Allow', 'Action': 'eks:DescribeNodegroup',
         'Resource': f'arn:aws:eks:{region}:{account}:nodegroup/{cluster}/*/*'},
    ]}
    return values, trust, policy


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=read_review_json, required=True)
    parser.add_argument('--output-dir', type=output_directory, required=True)
    args = parser.parse_args()
    try:
        values, trust, policy = prepare(args.config)
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        (args.output_dir / 'values.yml').write_text(yaml.safe_dump(values, sort_keys=False))
        (args.output_dir / 'iam-trust.json').write_text(json.dumps(trust, indent=2) + '\n')
        (args.output_dir / 'iam-policy.json').write_text(json.dumps(policy, indent=2) + '\n')
        # The reviewed upstream chart has liveness only; use standard Kustomize
        # patches for the missing startup/readiness and termination budget.
        patch = [
            {'op': 'add', 'path': '/spec/template/spec/terminationGracePeriodSeconds', 'value': 150},
            {'op': 'add', 'path': '/spec/template/spec/containers/0/startupProbe', 'value': {
                'httpGet': {'path': '/health-check', 'port': 8085}, 'periodSeconds': 10, 'timeoutSeconds': 3, 'failureThreshold': 30}},
            {'op': 'add', 'path': '/spec/template/spec/containers/0/readinessProbe', 'value': {
                'httpGet': {'path': '/health-check', 'port': 8085}, 'periodSeconds': 10, 'timeoutSeconds': 3}},
        ]
        (args.output_dir / 'reliability-patch.yml').write_text(yaml.safe_dump(patch, sort_keys=False))
        (args.output_dir / 'kustomization.yml').write_text(yaml.safe_dump({
            'apiVersion': 'kustomize.config.k8s.io/v1beta1', 'kind': 'Kustomization',
            'resources': ['upstream.yml'], 'patches': [{'path': 'reliability-patch.yml',
                'target': {'group': 'apps', 'version': 'v1', 'kind': 'Deployment', 'labelSelector': 'cloudforge.ai/component=node-autoscaler'}}],
        }, sort_keys=False))
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, 'Invalid node autoscaler inputs or output directory; no deployment performed.\n')
