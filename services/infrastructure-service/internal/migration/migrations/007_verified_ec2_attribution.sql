CREATE TABLE IF NOT EXISTS infrastructure_ec2_attribution (
    resource_id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    environment TEXT NOT NULL,
    region TEXT NOT NULL,
    account_id TEXT NOT NULL CHECK (account_id ~ '^[0-9]{12}$'),
    instance_id TEXT NOT NULL CHECK (instance_id ~ '^i-([0-9a-f]{8}|[0-9a-f]{17})$'),
    verified_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (account_id, region, instance_id)
);
CREATE INDEX IF NOT EXISTS infrastructure_ec2_attribution_project_idx
    ON infrastructure_ec2_attribution(project_id);
