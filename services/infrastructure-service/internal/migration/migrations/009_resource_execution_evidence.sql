ALTER TABLE infrastructure_resources
    ADD COLUMN terraform_resource_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN last_execution_error TEXT NOT NULL DEFAULT '';
