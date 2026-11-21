# CloudForge AWS bootstrap

Use an approved bootstrap identity in the intended account. The state bucket and IAM roles are separate from application resources. Bootstrap itself uses local state. Store the bootstrap state and saved plans privately and retain a recovery copy.

```sh
cd infrastructure/terraform/bootstrap
export AWS_REGION=eu-west-1 TF_VAR_aws_region=eu-west-1
export TF_VAR_account_id="$(aws sts get-caller-identity --region "$AWS_REGION" --query Account --output text)"
export TF_VAR_state_access_log_bucket_name="${APPROVED_STATE_ACCESS_LOG_BUCKET:?set an approved existing log bucket}"
export TF_VAR_state_bucket_name="cloudforge-ai-${TF_VAR_account_id}-tfstate"

# For an existing EKS cluster with its IAM OIDC provider already registered
issuer="$(aws eks describe-cluster --region "$AWS_REGION" --name "${EKS_CLUSTER_NAME:?}" --query cluster.identity.oidc.issuer --output text)"
export TF_VAR_runtime_oidc_provider_arn="arn:aws:iam::${TF_VAR_account_id}:oidc-provider/${issuer#https://}"
unset TF_VAR_runtime_principal_arn
# For non-EKS workloads, instead unset TF_VAR_runtime_oidc_provider_arn
# and validate the approved workload role before exporting its ARN.
# aws iam get-role --role-name "${WORKLOAD_ROLE_NAME:?}" --query Role.Arn --output text
# export TF_VAR_runtime_principal_arn="${WORKLOAD_ROLE_ARN:?}"

terraform init -backend=false
terraform validate
terraform plan -out=bootstrap.tfplan
# Only after explicit approval of this saved plan
terraform apply bootstrap.tfplan
```

Configure the existing infrastructure service using the bootstrap outputs.

```sh
export TERRAFORM_STATE_BUCKET="$(terraform output -raw terraform_state_bucket_name)"
export TERRAFORM_STATE_REGION="$AWS_REGION"
export TERRAFORM_PROVISIONER_ROLE_ARN="$(terraform output -raw terraform_provisioner_role_arn)"
terraform output -raw infrastructure_service_runtime_role_arn
```

For EKS, set the three variables in the `cloudforge-terraform` ConfigMap and use the runtime role output on the `cloudforge/cloudforge-infrastructure-service` service account. For non-EKS workloads, configure the credential provider to assume the runtime role before starting the service. The S3 backend uses the runtime role. The generated AWS provider assumes the provisioner role. Do not set static AWS access keys. Supply database and frontend-signing values through the manifest's existing Kubernetes Secret references. If sourced from Secrets Manager, have the deployment secret controller synchronize those keys using its own role scoped to the named secret ARNs and any required KMS key.

Verify bucket controls without printing state or writing lockfiles.

```sh
aws s3api get-bucket-location --bucket "$TERRAFORM_STATE_BUCKET" --expected-bucket-owner "$TF_VAR_account_id"
aws s3api get-bucket-versioning --bucket "$TERRAFORM_STATE_BUCKET" --expected-bucket-owner "$TF_VAR_account_id"
aws s3api get-bucket-encryption --bucket "$TERRAFORM_STATE_BUCKET" --expected-bucket-owner "$TF_VAR_account_id"
aws s3api get-public-access-block --bucket "$TERRAFORM_STATE_BUCKET" --expected-bucket-owner "$TF_VAR_account_id"
```

Review the workload's effective state and lockfile permissions before its first approved plan. Regenerate saved plans after changing backend or provider role. Scoped provisioning permissions apply in the bootstrap region. Reserve `cloudforge-*` application bucket names and the CloudForge EKS and RDS name/role namespaces for this provisioner. Role-bound requests use UUID-based EKS and RDS names. Stop if an existing legacy resource would be renamed or replaced, and reconcile its state and IAM first. For the S3 smoke test use a unique, empty `cloudforge-*` bucket with `force_destroy=false`. The provisioner has no blanket object-deletion permission.

Apply success requires a Terraform state ID and a provider refresh consistent with that state. The API continues to report current live AWS health as unverified. Destroy success requires empty managed state. After partial execution, retain the record, refresh through the destroy planning workflow, review the new saved plan and obtain a fresh approval before executing it. Run live provisioning and teardown only in an approved sandbox account.

## Approved live verification and cleanup

Run these checks under the intended workload credentials. Run the Secrets Manager check under the secret controller's identity with its exact secret ARN. The command requests the secret but prints no payload. The controller should have scoped read access and any required KMS decrypt permission. Verify the published Kubernetes Secret references without dumping their data.

```sh
aws sts get-caller-identity --query Arn --output text
aws s3api list-objects-v2 --bucket "$TERRAFORM_STATE_BUCKET" --prefix cloudforge/resources/ --max-keys 1 --query KeyCount
aws secretsmanager get-secret-value --secret-id "${RUNTIME_SECRET_ARN:?}" --query VersionId --output text >/dev/null
```

Start with EC2 in a disposable project. Use read-only calls to resolve an Amazon Linux AMI and check the approved sandbox subnet. These commands have no AWS writes.

```sh
export SANDBOX_SUBNET_ID="${SANDBOX_SUBNET_ID:?Set an approved sandbox subnet}"
ami="$(aws ssm get-parameter --region "$AWS_REGION" --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)"
aws ec2 describe-images --region "$AWS_REGION" --image-ids "$ami" --query 'Images[].{AMI:ImageId,Architecture:Architecture,State:State}'
aws ec2 describe-subnets --region "$AWS_REGION" --subnet-ids "$SANDBOX_SUBNET_ID" --query 'Subnets[].{Subnet:SubnetId,VPC:VpcId,Zone:AvailabilityZone}'
printf '{"ami_id":"%s","subnet_id":"%s","instance_type":"t3.micro","associate_public_ip_address":false}\n' "$ami" "$SANDBOX_SUBNET_ID"
```

Paste that configuration into the CloudForge EC2 request and use the normal review cycle below. After approved Apply, use the Terraform state ID as `EC2_ID` for the read-only verification command. After approved cleanup, the command should show `terminated` or eventually return `InvalidInstanceID.NotFound`; authorization failures prove neither. Verify EC2 before moving on to VPC, S3, RDS and EKS.

Approve one resource at a time through the normal Infrastructure UI. Set an approved region-valid AMI and subnet for EC2, an unused CIDR for VPC, an empty S3 bucket, a Single-AZ PostgreSQL DB with a supported class, and valid same-VPC subnets in distinct availability zones for EKS. For a small EKS smoke test set one `t3.medium` worker. In the UI, save each plan, submit it, have a different operator review and approve it, and execute that approved revision only after explicit authorization. Confirm a provider state ID and a successful review outcome. Copy the returned IDs to the variables below. An AWS read error or missing ID is an unresolved verification result.

```sh
aws ec2 describe-instances --instance-ids "${EC2_ID:?}" --query 'Reservations[].Instances[].State.Name'
aws ec2 describe-vpcs --vpc-ids "${VPC_ID:?}" --query 'Vpcs[].State'
aws s3api head-bucket --bucket "${APPLICATION_BUCKET:?}" --expected-bucket-owner "$TF_VAR_account_id"
aws rds describe-db-instances --filters "Name=dbi-resource-id,Values=${RDS_STATE_ID:?}" --query 'DBInstances[].DBInstanceStatus'
aws eks describe-cluster --name "${EKS_NAME:?}" --query 'cluster.status'
aws eks describe-nodegroup --cluster-name "$EKS_NAME" --nodegroup-name default-pool --query 'nodegroup.status'
```

For RDS if Terraform reports the DB identifier instead of an AWS `db-…` resource ID, use `aws rds describe-db-instances --db-instance-identifier "$RDS_STATE_ID" --query 'DBInstances[].DBInstanceStatus'`. Check that the lockfile is absent after execution and investigate unexplained remaining locks. Lock acquisition itself involves an S3 write and is verified only during an authorized operation.

For cleanup, generate a fresh destroy plan per resource in dependency order (EKS and workloads first, standalone VPC last). Review the exact plan, secure independent approval and explicit authorization, then execute it through CloudForge. Repeat the read commands to verify deletion or terminal status; distinguish absence from access denial. Account for retained RDS snapshots, EBS volumes, logs, and S3 versions. Keep the bootstrap state bucket and IAM roles while projects use them. Reconcile partial failures through fresh planning and approval.

### Smoke-test estimate

For one billed hour in Ireland, queried on-demand rates give about **USD 0.174** for one Linux `t3.micro` ($0.0114), a Single-AZ PostgreSQL `db.t4g.micro` ($0.0170), one Linux `t3.medium` EKS worker ($0.0456), and one [standard-support EKS control plane](https://aws.amazon.com/eks/pricing/) ($0.10). This is compute/control plane only. Include storage, requests, snapshots, logs, taxes, network charges and [public IPv4](https://aws.amazon.com/vpc/pricing/) separately. Verify current prices in the [AWS Pricing Calculator](https://calculator.aws/) against the actual approved plan and duration.

## First EC2 in account 933018172228

Read-only discovery found IAM user `cloudforge-admin`, no general workload role, and no EKS cluster. A valid bootstrap plan requires an existing role to trust. The following workstation trust is a proposed local smoke-test setup. Review its named IAM principal before approving creation. Use the deployed workload's identity for production.

Prepare these local policy files from the repository root.

```sh
umask 077
mkdir -p /tmp/cloudforge-first-ec2
cat > /tmp/cloudforge-first-ec2/trust.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"arn:aws:iam::933018172228:user/cloudforge-admin"},"Action":"sts:AssumeRole"}]}
JSON
cat > /tmp/cloudforge-first-ec2/assume-runtime.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"sts:AssumeRole","Resource":"arn:aws:iam::933018172228:role/cloudforge-infrastructure-service-runtime"}]}
JSON
```

Stop for explicit approval before these IAM writes. The workload role has only permission to assume the runtime role. The signed UI approval remains mandatory for application execution.

```sh
aws iam create-role --role-name cloudforge-local-workload --assume-role-policy-document file:///tmp/cloudforge-first-ec2/trust.json
aws iam put-role-policy --role-name cloudforge-local-workload --policy-name AssumeCloudForgeRuntime --policy-document file:///tmp/cloudforge-first-ec2/assume-runtime.json
```

After approved role creation, generate the bootstrap plan using the verified account and region. Inspect the complete plan, especially trust, IAM policy scope, bucket encryption, versioning, public-access blocking, and lockfile permissions.

```sh
export AWS_REGION=eu-west-1
export TF_VAR_account_id=933018172228 TF_VAR_aws_region=eu-west-1
export TF_VAR_state_access_log_bucket_name="${APPROVED_STATE_ACCESS_LOG_BUCKET:?set an approved existing log bucket}"
export TF_VAR_state_bucket_name=cloudforge-ai-933018172228-tfstate
export TF_VAR_runtime_principal_arn=arn:aws:iam::933018172228:role/cloudforge-local-workload
unset TF_VAR_runtime_oidc_provider_arn
terraform -chdir=infrastructure/terraform/bootstrap init -backend=false
terraform -chdir=infrastructure/terraform/bootstrap validate
terraform -chdir=infrastructure/terraform/bootstrap plan -out=bootstrap.tfplan
terraform -chdir=infrastructure/terraform/bootstrap show -no-color bootstrap.tfplan
```

Stop again for explicit approval of that saved plan. Then execute only `terraform -chdir=infrastructure/terraform/bootstrap apply bootstrap.tfplan`. Use the bucket verification commands above afterward. Remote locking remains unverified until an approved execution acquires and releases its lock.

Configure AWS profile `cloudforge-local-workload` with its role ARN and a source profile for the verified administrator. Configure profile `cloudforge-runtime` with runtime role ARN `arn:aws:iam::933018172228:role/cloudforge-infrastructure-service-runtime` and `source_profile=cloudforge-local-workload`. Both profiles use `region=eu-west-1`. Avoid writing temporary credentials into Compose. Verify the role chain before enabling execution.

```sh
aws sts get-caller-identity --profile cloudforge-runtime --query Arn --output text
export TERRAFORM_READ_ONLY=false
export TERRAFORM_STATE_BUCKET=cloudforge-ai-933018172228-tfstate
export TERRAFORM_STATE_REGION=eu-west-1
export TERRAFORM_PROVISIONER_ROLE_ARN=arn:aws:iam::933018172228:role/cloudforge-terraform-provisioner
export AWS_PROFILE=cloudforge-runtime
export AWS_ACCESS_KEY_ID="" AWS_SECRET_ACCESS_KEY="" AWS_SESSION_TOKEN=""
docker compose config --quiet
docker compose up -d --no-build --no-deps infrastructure-service
```

Review any static credential entries in the ignored local environment file before recreation. Confirm the effective service identity through the role chain. This configuration is prepared only; local Terraform execution stays read-only until bootstrap is approved and verified.

In the UI, create a disposable project as Developer A. Confirm Developer B cannot see it. Request EC2 with `t3.micro`, public IP disabled, and an explicitly approved subnet. Discovery returned `subnet-08285f40adb0c8835`, `subnet-0251fae570fd83a7e`, and `subnet-02383ec1e150938ab`. Select one after reviewing its VPC and network policy. Resolve the AMI again with the SSM command above; discovery returned `ami-0f660e8e338a08db5`. Save, generate and submit the plan. A separate Platform Engineer reviews it. Obtain explicit apply authorization before execution.

After Apply, copy the state ID from the resource UI and verify it independently.

```sh
aws ec2 describe-instances --region eu-west-1 --instance-ids "${EC2_ID:?Copy the returned instance ID}" --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name,Subnet:SubnetId,Tags:Tags}'
```

Check review history and errors, retain failed records, and generate a fresh approval-bound plan for recovery. For cleanup, generate the UI destroy plan, obtain independent review and explicit destroy authorization, then execute and repeat the read command to verify termination. Check for retained EBS volumes and snapshots. Preserve the state backend and workload roles while other projects use them.

Budget roughly USD 0.02–0.05 for a one-hour, single-instance smoke test including a small root disk, excluding taxes and unusual transfer or CPU-credit charges. Confirm current EC2 and disk prices before approval. Bootstrap S3 storage, requests, and retained state versions add usage charges.

## Release foundation allowlists

Before generating a new bootstrap plan, set `application_bucket_names` to the exact
reviewed application bucket names. Its default empty set now disables application
S3 lifecycle permissions; the state bucket must never be included. Preserve names
of existing managed application buckets when upgrading this policy. Inspect the
policy diff before approval to avoid inadvertently removing required access.

For External Secrets Operator, set `secret_sync_secret_arns` to the exact existing
same-account/region Secrets Manager ARNs used by the Kubernetes renderer and set
`secret_sync_kms_key_arns` only for their customer-managed KMS keys. This requires
`runtime_oidc_provider_arn`; the optional role trusts only
`cloudforge/cloudforge-secret-sync` with the STS audience. Use the resulting
`secret_sync_role_arn` in the renderer's `roles.secret-sync`. This creates neither
secrets nor a controller. The FinOps read-only role, secret-controller Kubernetes
permissions, OIDC provider and live endpoint access remain explicit prerequisites.
An empty secret list creates no sync role. Review a saved bootstrap plan before any
separately authorized IAM/state changes; no apply is part of local validation.

State access logging requires an approved existing destination bucket in the same
account/region, with public access blocked, encryption, retention and a
`logging.s3.amazonaws.com` delivery policy restricted to the state bucket ARN and
source account. This bootstrap does not create or verify that external destination;
verify it read-only before approving the plan. State and log buckets must differ.
No cloud changes are authorized by these instructions.
