# Pinned controller source

installation-inputs.json defines proposed version/image/configuration pins and
checksums of vendored public source. No copied compatibility verdict, account
snapshot, managed-policy readback, Helm archive or installation receipt is used.
All live compatibility, IAM/security and regional eligibility acceptance is
UNVERIFIED until separately checked. This directory performs no installation.

The chart templates are the unchanged aws-load-balancer-controller1.14.1 chart
(application2.14.1); README trailing whitespace alone is normalized and its
archive is excluded. Core CRDs, vendor schemas, feature
exclusions and the TGB-only policy template retain their reviewed content. Upstream:
https://github.com/aws/eks-charts/tree/master/stable/aws-load-balancer-controller
https://github.com/kubernetes-sigs/aws-load-balancer-controller/tree/v2.14.1
Schemas are public add-on configuration definitions for the exact pinned versions;
they are not account/cluster observations or proof of current availability.

Use preview config (one EFS controller, both EBS controllers), not a historical
full-HA controller count. The scoped target-group policy intentionally has a null
Resource; bind the actual private target group and reviewed trust before use.
AWS managed-policy ARNs in the operator template are references, not immutable
policy documents or current approvals. No cached policy/registry/account evidence
is included. Unknowns block deployment.
