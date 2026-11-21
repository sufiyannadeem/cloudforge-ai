export type InfrastructureValues = Record<string, string | boolean>;

type Field = {
  key: string;
  label: string;
  value: string | boolean;
  required?: boolean;
  pattern?: string;
  min?: number;
  max?: number;
  list?: boolean;
  options?: readonly string[];
  hint?: string;
};

const instanceType = "[a-z][a-z0-9-]*\\.[a-z0-9-]+";
const subnet = "subnet-(?:[0-9a-f]{8}|[0-9a-f]{17})";
const subnets: Field = { key: "subnet_ids", label: "Subnet IDs", value: "", list: true, pattern: subnet, hint: "Enter comma-separated subnets from different availability zones." };

export const infrastructureFields: Record<string, readonly Field[]> = {
  aws_ec2: [
    { key: "ami_id", label: "Amazon Machine Image (AMI)", value: "resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64", required: true, pattern: "(?:ami-(?:[0-9a-f]{8}|[0-9a-f]{17})|resolve:ssm:/aws/service/ami-amazon-linux-latest/[a-z0-9_-]+)", hint: "Defaults to Amazon Linux 2023 (x86-64). You can supply a region-valid AMI ID instead." },
    { key: "instance_type", label: "Instance type", value: "t3.micro", pattern: instanceType, required: true },
    { key: "subnet_id", label: "Subnet ID", value: "", pattern: subnet, required: true },
    { key: "security_group_ids", label: "Security group IDs (optional)", value: "", list: true, pattern: "sg-(?:[0-9a-f]{8}|[0-9a-f]{17})" },
    { key: "associate_public_ip_address", label: "Assign a public IPv4 address", value: false },
  ],
  aws_vpc: [
    { key: "cidr_block", label: "IPv4 CIDR", value: "10.0.0.0/16", required: true, hint: "Use an available IPv4 network with a prefix from /16 to /28." },
    { key: "enable_dns_support", label: "Enable DNS resolution", value: true },
    { key: "enable_dns_hostnames", label: "Enable DNS hostnames", value: true },
  ],
  aws_s3: [
    { key: "bucket", label: "Globally unique bucket name", value: "", pattern: "cloudforge-[a-z0-9]+(?:-[a-z0-9]+)*", required: true, hint: "Use the cloudforge- prefix and up to 63 characters." },
    { key: "versioning", label: "Keep object versions", value: true },
  ],
  aws_rds: [
    { key: "engine", label: "Database engine", value: "postgres", options: ["postgres", "mysql", "mariadb"] },
    { key: "engine_version", label: "Engine version (optional)", value: "", pattern: "[0-9]+(?:\\.[0-9]+){0,3}", hint: "Leave blank to use the AWS default." },
    { key: "instance_class", label: "DB instance class", value: "db.t4g.micro", pattern: "db\\." + instanceType, required: true },
    { key: "allocated_storage", label: "Allocated storage (GiB)", value: "20", min: 20, max: 1000, required: true },
    { key: "database_name", label: "Initial database name", value: "cloudforge", pattern: "[A-Za-z][A-Za-z0-9]{0,62}", required: true },
    { ...subnets, required: true },
    { key: "multi_az", label: "Enable Multi-AZ", value: false },
  ],
  aws_eks: [
    { ...subnets, required: true },
    { key: "cluster_version", label: "Kubernetes version (optional)", value: "", pattern: "1\\.[0-9]+", hint: "Leave blank to use the AWS default." },
    { key: "node_instance_types", label: "Worker instance types", value: "t3.medium", list: true, pattern: instanceType, required: true },
    { key: "min_capacity", label: "Minimum workers", value: "1", min: 0, max: 100, required: true },
    { key: "desired_capacity", label: "Desired workers", value: "1", min: 0, max: 100, required: true },
    { key: "max_capacity", label: "Maximum workers", value: "2", min: 1, max: 100, required: true },
  ],
  aws_lb: [
    { ...subnets, required: true },
    { key: "internal", label: "Internal load balancer", value: true },
    { key: "port", label: "Listener port", value: "80", min: 1, max: 65535, required: true },
  ],
};

export function defaultInfrastructureValues(type: string): InfrastructureValues {
  return Object.fromEntries((infrastructureFields[type] ?? []).map(({ key, value }) => [key, value]));
}

export function infrastructureConfiguration(type: string, values: InfrastructureValues) {
  const fields = infrastructureFields[type];
  if (!fields) throw new Error("Select a supported resource type.");
  const config: Record<string, string | boolean | number | string[]> = {};
  for (const field of fields) {
    const value = values[field.key] ?? field.value;
    if (typeof value === "boolean") {
      config[field.key] = value;
      continue;
    }
    const text = value.trim();
    if (!text) {
      if (field.required) throw new Error(`Enter ${field.label}.`);
      continue;
    }
    const items = field.list ? text.split(",").map((item) => item.trim()) : [text];
    if (field.pattern && items.some((item) => !new RegExp(`^(?:${field.pattern})$`).test(item))) {
      throw new Error(`Check ${field.label}.`);
    }
    if (field.options && !field.options.includes(text)) throw new Error(`Check ${field.label}.`);
    if (field.min !== undefined) {
      const number = Number(text);
      if (!/^\d+$/.test(text) || !Number.isSafeInteger(number) || number < field.min || number > (field.max ?? Infinity)) {
        throw new Error(`${field.label} must be between ${field.min} and ${field.max}.`);
      }
      config[field.key] = number;
    } else {
      config[field.key] = field.list ? items : text;
    }
  }
  if (type === "aws_vpc") {
    const [address, prefix, ...extra] = String(config.cidr_block).split("/");
    const octets = address.split(".");
    if (extra.length || octets.length !== 4 || octets.some((x) => !/^\d{1,3}$/.test(x) || Number(x) > 255) ||
        !/^(1[6-9]|2[0-8])$/.test(prefix ?? "")) throw new Error("Enter a valid IPv4 CIDR with a /16 to /28 prefix.");
    if (config.enable_dns_hostnames && !config.enable_dns_support) throw new Error("Enable DNS resolution before enabling DNS hostnames.");
  }
  const ids = config.subnet_ids;
  if (Array.isArray(ids) && (ids.length < 2 || new Set(ids).size !== ids.length)) {
    throw new Error("Enter at least two distinct subnet IDs.");
  }
  if (type === "aws_s3") {
    if (String(config.bucket).length > 63) throw new Error("Bucket name must be 63 characters or fewer.");
    config.force_destroy = false;
  }
  if (type === "aws_rds") config.skip_final_snapshot = false;
  if (type === "aws_eks" && !(Number(config.min_capacity) <= Number(config.desired_capacity) && Number(config.desired_capacity) <= Number(config.max_capacity))) {
    throw new Error("Set minimum workers ≤ desired workers ≤ maximum workers.");
  }
  if (type === "aws_lb") {
    config.load_balancer_type = "application";
    config.protocol = "HTTP";
  }
  return config;
}
