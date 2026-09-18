CREATE TABLE IF NOT EXISTS infrastructure_resources (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    provider VARCHAR(50) NOT NULL,
    region VARCHAR(100) NOT NULL,
    environment VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    terraform_directory TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT infrastructure_resources_name_check
        CHECK (char_length(trim(name)) >= 3),

    CONSTRAINT infrastructure_resources_provider_check
        CHECK (provider IN ('aws', 'azure', 'gcp', 'local')),

    CONSTRAINT infrastructure_resources_status_check
        CHECK (status IN ('active', 'inactive', 'provisioning', 'destroying', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_infrastructure_resources_provider
    ON infrastructure_resources(provider);

CREATE INDEX IF NOT EXISTS idx_infrastructure_resources_environment
    ON infrastructure_resources(environment);

CREATE INDEX IF NOT EXISTS idx_infrastructure_resources_status
    ON infrastructure_resources(status);
