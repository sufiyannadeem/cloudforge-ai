ALTER TABLE infrastructure_resources
    ADD COLUMN IF NOT EXISTS project_id UUID,
    ADD COLUMN IF NOT EXISTS resource_type TEXT,
    ADD COLUMN IF NOT EXISTS configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS plan_path TEXT,
    ADD COLUMN IF NOT EXISTS plan_hash TEXT,
    ADD COLUMN IF NOT EXISTS plan_created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approval_expires_at TIMESTAMPTZ;

ALTER TABLE infrastructure_resources
    DROP CONSTRAINT IF EXISTS infrastructure_resources_status_check;

ALTER TABLE infrastructure_resources
    ADD CONSTRAINT infrastructure_resources_status_check
    CHECK (
        status IN (
            'pending',
            'planning',
            'awaiting_approval',
            'provisioning',
            'active',
            'inactive',
            'destroying',
            'failed',
            'destroyed'
        )
    );

ALTER TABLE infrastructure_resources
    ADD CONSTRAINT infrastructure_resources_resource_type_check
    CHECK (
        resource_type IS NULL
        OR resource_type IN (
            'aws_vpc',
            'aws_ec2',
            'aws_s3'
        )
    );

CREATE INDEX IF NOT EXISTS idx_infrastructure_resources_project_id
    ON infrastructure_resources(project_id);

CREATE INDEX IF NOT EXISTS idx_infrastructure_resources_status
    ON infrastructure_resources(status);
