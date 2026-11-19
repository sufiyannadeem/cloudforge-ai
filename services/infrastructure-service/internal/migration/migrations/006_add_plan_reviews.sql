ALTER TABLE infrastructure_resources
    ADD COLUMN IF NOT EXISTS requested_by TEXT,
    ADD COLUMN IF NOT EXISTS destroy_requested_by TEXT;

CREATE TABLE IF NOT EXISTS infrastructure_plan_reviews (
    resource_id UUID NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('apply', 'destroy')),
    revision TIMESTAMPTZ NOT NULL,
    plan_hash TEXT NOT NULL,
    project_id UUID NOT NULL,
    environment TEXT NOT NULL,
    requester TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('submitted', 'approved', 'rejected', 'executing', 'failed', 'succeeded')),
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    executed_by TEXT,
    execution_started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    PRIMARY KEY (resource_id, operation, revision)
);
