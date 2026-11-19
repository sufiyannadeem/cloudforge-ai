ALTER TABLE infrastructure_resources ADD COLUMN plan_started_active boolean NOT NULL DEFAULT false;

CREATE TABLE terraform_drift_scans (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_id uuid NOT NULL REFERENCES infrastructure_resources(id) ON DELETE CASCADE,
    actor text NOT NULL,
    status text NOT NULL CHECK (status IN ('observed', 'unavailable')),
    findings jsonb NOT NULL,
    scanned_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX terraform_drift_resource_history
    ON terraform_drift_scans (resource_id, id DESC);
