CREATE TABLE deployment_diagnostics (
    id UUID PRIMARY KEY,
    deployment_id UUID NOT NULL REFERENCES deployments(id) ON DELETE CASCADE,
    actor TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    evidence JSONB NOT NULL CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE INDEX deployment_diagnostics_history_idx ON deployment_diagnostics (deployment_id, captured_at DESC, id DESC);
