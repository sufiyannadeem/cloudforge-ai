ALTER TABLE deployments ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'unknown'
    CHECK (execution_mode IN ('unknown', 'simulated', 'kubernetes'));

ALTER TABLE deployment_attempts ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'unknown'
    CHECK (execution_mode IN ('unknown', 'simulated', 'kubernetes'));
