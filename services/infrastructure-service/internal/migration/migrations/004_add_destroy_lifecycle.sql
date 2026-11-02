-- Teardown lifecycle: hashed destroy plan artifacts and the human-approval
-- state that gates `terraform apply destroy.tfplan`.
ALTER TABLE infrastructure_resources
    ADD COLUMN IF NOT EXISTS destroy_plan_path TEXT,
    ADD COLUMN IF NOT EXISTS destroy_plan_hash TEXT;

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
            'awaiting_destroy_approval',
            'failed',
            'destroyed'
        )
    );
