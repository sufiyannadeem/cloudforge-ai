import assert from "node:assert/strict";
import test from "node:test";
import { defaultInfrastructureValues, infrastructureConfiguration } from "../src/lib/infrastructure-form.ts";

const a = "subnet-11111111";
const b = "subnet-22222222";
const config = (type, values = {}) => infrastructureConfiguration(type, { ...defaultInfrastructureValues(type), ...values });

test("valid guided forms create AWS configurations with safe defaults", () => {
  assert.equal(config("aws_ec2", { subnet_id: a }).associate_public_ip_address, false);
  assert.match(config("aws_ec2", { subnet_id: a }).ami_id, /^resolve:ssm:\/aws\/service\//);
  assert.equal(config("aws_vpc").cidr_block, "10.0.0.0/16");
  assert.deepEqual(config("aws_s3", { bucket: "cloudforge-private-example" }), {
    bucket: "cloudforge-private-example", versioning: true, force_destroy: false,
  });
  assert.equal(config("aws_rds", { subnet_ids: `${a}, ${b}` }).skip_final_snapshot, false);
  assert.deepEqual(config("aws_eks", { subnet_ids: `${a}, ${b}` }).subnet_ids, [a, b]);
  assert.equal(config("aws_eks", { subnet_ids: `${a}, ${b}` }).desired_capacity, 1);
  assert.equal(config("aws_lb", { subnet_ids: `${a}, ${b}` }).internal, true);
});

test("invalid inputs and cross-field combinations are rejected", () => {
  assert.throws(() => config("aws_ec2", { subnet_id: a, ami_id: "not-an-ami" }), /Amazon Machine Image/);
  assert.throws(() => config("aws_vpc", { cidr_block: "300.0.0.0/16" }), /IPv4 CIDR/);
  assert.throws(() => config("aws_s3", { bucket: "other-app" }), /bucket name/);
  assert.throws(() => config("aws_rds", { subnet_ids: a }), /two distinct/);
  assert.throws(() => config("aws_eks", { subnet_ids: `${a}, ${a}` }), /two distinct/);
  assert.throws(() => config("aws_eks", { subnet_ids: `${a}, ${b}`, desired_capacity: "3" }), /desired workers/);
});
