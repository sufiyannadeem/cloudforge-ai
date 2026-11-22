# Restricted preview source inputs

These are reviewed configuration/templates and declared resource models, not
account observations, current quotes, deployment approval or compatibility proof.
The canonical Terraform example is
`../../infrastructure/terraform/environments/dev/free-plan.tfvars.example`:
two fixed m6a.large workers, no scale-out. Use the deployment binding template's
serialized-no-surge mode, all six applications fixed2, single EFS CSI controller
from `../controllers/config/aws-efs-csi-driver-configuration.json`, and ordered
migrations with applications stopped. Baseline scheduling is a regression model,
not an alternative deployment recommendation. Security, database durability and
Free-plan exclusions remain unchanged. No ESO/MSK/Kafka/AI/drift/Rollouts or tenant
Terraform execution is authorized.

All account, IAM, CIDR, secret, storage and CA fields remain unbound. Supply real
reviewed values privately; do not place credentials or account snapshots here.
The RDS bundle must be supplied and verified against the actual endpoint/CA.
Monitoring requires the named preseeded TLS/admin/identity secrets and trusted CA;
never disable verification or relax network policy to make an unbound test pass.

`render-preview-monitoring.py` reads monitoring-budget.json as declared source.
`compare-preview-capacity.py` and `check-preview-safety.py` require explicit
`--catalog PATH --evidence PATH` inputs from outside source. Inputs older than24h
or future-dated are rejected; absent observations never fall back to packaged
prices/account data. Outputs remain NO-GO until independent live gates pass.
Tests use invented fixtures and cannot authorize deployment.

Preserve the $105 spending cap, $29 reserve and five-day maximum. Billing stop
thresholds must be derived from the actual balance and costs, retaining cleanup
and billing-lag buffers. No historical price/balance is a current quote or hard
AWS cap. Real account eligibility, quotas, capacity, load behavior, certificates,
controller/CSI/network acceptance and teardown remain operator prerequisites.
