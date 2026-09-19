CREATE TABLE IF NOT EXISTS deployment_attempts (
    id UUID PRIMARY KEY,
    deployment_id UUID NOT NULL,
    attempt_number INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT deployment_attempts_deployment_fk
        FOREIGN KEY (deployment_id)
        REFERENCES deployments(id)
        ON DELETE CASCADE,

    CONSTRAINT deployment_attempts_attempt_number_check
        CHECK (attempt_number > 0),

    CONSTRAINT deployment_attempts_status_check
        CHECK (status IN (
            'running',
            'succeeded',
            'failed',
            'cancelled'
        )),

    CONSTRAINT deployment_attempts_time_check
        CHECK (
            completed_at IS NULL
            OR completed_at >= started_at
        ),

    CONSTRAINT deployment_attempts_unique_number
        UNIQUE (deployment_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_deployment_attempts_deployment_id
    ON deployment_attempts(deployment_id);

CREATE INDEX IF NOT EXISTS idx_deployment_attempts_status
    ON deployment_attempts(status);

CREATE INDEX IF NOT EXISTS idx_deployment_attempts_started_at
    ON deployment_attempts(started_at DESC);
