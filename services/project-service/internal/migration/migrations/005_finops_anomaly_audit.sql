CREATE TABLE finops_anomaly_captures (
    id UUID PRIMARY KEY,
    account_id TEXT NOT NULL CHECK (account_id ~ '^[0-9]{12}$'),
    actor TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    evidence JSONB NOT NULL CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE INDEX finops_anomaly_capture_history_idx ON finops_anomaly_captures (account_id, captured_at DESC, id DESC);
