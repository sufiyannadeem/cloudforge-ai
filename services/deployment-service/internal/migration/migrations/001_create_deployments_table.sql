CREATE TABLE IF NOT EXISTS deployments (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    environment VARCHAR(50) NOT NULL,
    image TEXT NOT NULL,
    git_commit_sha VARCHAR(100) NOT NULL,
    namespace VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT deployments_environment_check
        CHECK (environment IN ('development', 'staging', 'production')),

    CONSTRAINT deployments_status_check
        CHECK (status IN (
            'pending',
            'queued',
            'running',
            'succeeded',
            'failed',
            'cancelled'
        )),

    CONSTRAINT deployments_image_check
        CHECK (char_length(trim(image)) >= 3),

    CONSTRAINT deployments_namespace_check
        CHECK (char_length(trim(namespace)) >= 1),

    CONSTRAINT deployments_git_commit_sha_check
        CHECK (char_length(trim(git_commit_sha)) >= 7)
);

CREATE INDEX IF NOT EXISTS idx_deployments_project_id
    ON deployments(project_id);

CREATE INDEX IF NOT EXISTS idx_deployments_environment
    ON deployments(environment);

CREATE INDEX IF NOT EXISTS idx_deployments_status
    ON deployments(status);

CREATE INDEX IF NOT EXISTS idx_deployments_created_at
    ON deployments(created_at DESC);
