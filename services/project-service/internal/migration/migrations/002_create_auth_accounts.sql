CREATE TABLE IF NOT EXISTS auth_users (
    username TEXT PRIMARY KEY CHECK (username ~ '^[a-z0-9][a-z0-9._@-]{0,127}$'),
    role TEXT NOT NULL CHECK (role IN ('platform-engineer', 'sre', 'developer')),
    password_hash BYTEA NOT NULL CHECK (octet_length(password_hash) = 32),
    password_salt BYTEA NOT NULL CHECK (octet_length(password_salt) = 32),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    session_version BIGINT NOT NULL DEFAULT 1,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    login_locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash BYTEA PRIMARY KEY CHECK (octet_length(token_hash) = 32),
    username TEXT NOT NULL REFERENCES auth_users(username) ON DELETE CASCADE,
    user_version BIGINT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON auth_sessions (expires_at);
