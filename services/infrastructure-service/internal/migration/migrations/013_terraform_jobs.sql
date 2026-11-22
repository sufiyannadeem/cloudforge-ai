-- Durable intake; running work is never automatically replayed after a crash.
CREATE TABLE infrastructure_jobs (
    id UUID PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES infrastructure_resources(id),
    path TEXT NOT NULL,
    body BYTEA NOT NULL,
    claims JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','interrupted')),
    response JSONB,
    response_code INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    deadline TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp() + interval '5 minutes'
);
CREATE UNIQUE INDEX infrastructure_jobs_one_active ON infrastructure_jobs(resource_id)
    WHERE status IN ('queued','running');
