ALTER TABLE deployments
    ADD COLUMN execution_token UUID,
    ADD COLUMN execution_expires_at TIMESTAMPTZ,
    ADD COLUMN execution_started BOOLEAN NOT NULL DEFAULT FALSE,
    ADD CONSTRAINT deployments_execution_lease_check
        CHECK ((execution_token IS NULL) = (execution_expires_at IS NULL));

CREATE INDEX deployments_execution_queue_idx
    ON deployments (updated_at, id)
    WHERE status IN ('queued', 'running');
