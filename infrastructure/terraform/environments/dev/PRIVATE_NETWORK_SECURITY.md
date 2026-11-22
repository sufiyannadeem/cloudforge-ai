# Private ingress and security exceptions

Public application traffic follows HTTPS API Gateway → VPC Link → internal ALB
HTTP80 → private frontend pods HTTP3000. API Gateway's default execute-api
endpoint provides client TLS; the ALB is not internet-facing. ALB ingress allows
only the VPC Link SG, VPC Link egress allows only ALB80, and ALB egress only private
frontend3000. Invalid ALB headers are dropped. No public ALB/listener is created.

## AVD-AWS-0054 — one expiring resource exception

The annotation immediately before **aws_lb_listener.internal_http** in
api_gateway.tf applies only to that listener and only to AVD-AWS-0054. It expires
**2026-12-22**. It is not a file, directory or global suppression. Global Trivy
severity, scanners and gates are unchanged; other HTTP listeners must still fail.

This is an explicit transport tradeoff, not a claim that VPC HTTP is encrypted.
API Gateway terminates public TLS and the existing private integration uses HTTP;
adding ALB TLS/certificates would change the requested transport/certificate
lifecycle. A VPC-level observer or sufficiently privileged compromised resource
could see private-hop content. The bounded source/destination SG identities,
private subnets, internal scheme and default-deny application policies are required
compensating controls. No credential/session payload may be logged. The exception
must be re-reviewed before expiry or any listener, SG, subnet, API integration or
certificate-lifecycle change. Do not extend it automatically or add a global ID.
If those controls cannot be established on the actual target, deployment is blocked.

Regression checks assert this topology, prove removing this annotation restores
AWS-0054, and require an unrelated deliberately unsafe fixture to trigger all five
AWS checks. EFS/RDS must retain stateful replies without blanket outbound rules;
no AWS-0104, AWS-0040, AWS-0041 or AWS-0052 exception is allowed.

## EKS management and service traffic

The EKS management endpoint is always private; the legacy public toggle must be
false and legacy public CIDRs empty. The resource explicitly sets the otherwise
inert public allowlist to the VPC CIDR to avoid AWS's default0.0.0.0/0. That list
**does not authorize private endpoint access**. An existing VPC-connected
operator needs working private routing/DNS, the reviewed operator IAM access entry
and its real SG ID. Only that SG gets TCP443 ingress on the additional control-plane
SG. No new operator compute, bastion, VPN, public endpoint or chargeable service
is provisioned by this change. Missing operator identity/network bindings fail closed.

The additional control-plane SG initiates traffic only to private node subnet
CIDRs: TCP443/10250 for API/kubelet, TCP9443 for LBC admission, TCP10251 for the
managed metrics-server API, and TCP/UDP53 for DNS. Real installed addon ports,
webhook reachability and private operator access require target acceptance.
Storage SGs have explicit egress=[]: PostgreSQL/EFS return traffic uses the
statefulness of allowed inbound5432/2049 connections. Database durability,
encryption, backup settings and EFS persistence are unchanged.

**Important boundary:** AWS EKS also creates/attaches its own cluster SG with
service-managed default rules. These Terraform edits restrict the explicitly
managed additional SG; SG permissions are a union, so they do not revoke a broad
rule on another attached SG. Actual generated-cluster/node SG rules and required
node registry/NAT egress remain a mandatory live review before deployment. Do not
claim that a clean source scan proves effective AWS SG isolation, or add local-exec
AWS rule mutations to conceal that prerequisite. No AWS account was accessed here.

References:
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html
- https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html
- https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html
