CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name VARCHAR(100) NOT NULL,
    description TEXT,

    repository_url TEXT NOT NULL,
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',

    status VARCHAR(30) NOT NULL DEFAULT 'active',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT projects_name_not_empty
        CHECK (LENGTH(TRIM(name)) > 0),

    CONSTRAINT projects_status_valid
        CHECK (status IN ('active', 'inactive', 'archived'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name_unique
    ON projects (LOWER(name));

CREATE INDEX IF NOT EXISTS idx_projects_status
    ON projects (status);

CREATE INDEX IF NOT EXISTS idx_projects_created_at
    ON projects (created_at DESC);
