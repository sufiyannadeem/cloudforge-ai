CREATE TABLE IF NOT EXISTS infrastructure_execution_leases (
    resource_id UUID PRIMARY KEY REFERENCES infrastructure_resources(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('plan', 'apply', 'plan_destroy', 'apply_destroy')),
    fencing_token BIGINT NOT NULL DEFAULT 1,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_infrastructure_execution_leases_expires
    ON infrastructure_execution_leases(lease_expires_at);
