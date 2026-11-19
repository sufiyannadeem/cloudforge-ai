CREATE TABLE IF NOT EXISTS infrastructure_approval_assertions (
    nonce TEXT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS infrastructure_approval_assertions_expiry_idx
    ON infrastructure_approval_assertions (expires_at);
