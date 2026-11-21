ALTER TABLE infrastructure_resources DROP CONSTRAINT infrastructure_resources_status_check;

ALTER TABLE infrastructure_resources ADD CONSTRAINT infrastructure_resources_status_check
    CHECK (status IN ('pending', 'planning', 'awaiting_approval', 'provisioning',
        'active', 'inactive', 'destroying', 'awaiting_destroy_approval', 'failed',
        'destroyed', 'destroy_failed'));

UPDATE infrastructure_resources r
SET status = 'destroy_failed', updated_at = GREATEST(clock_timestamp(), r.updated_at + interval '1 microsecond')
WHERE status = 'active' AND (
    SELECT v.operation = 'destroy' AND v.status = 'failed'
    FROM infrastructure_plan_reviews v
    WHERE v.resource_id = r.id AND v.finished_at IS NOT NULL
    ORDER BY v.finished_at DESC
    LIMIT 1
);
