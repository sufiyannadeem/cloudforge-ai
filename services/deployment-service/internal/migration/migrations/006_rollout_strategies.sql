ALTER TABLE deployments
 ADD COLUMN strategy JSONB NOT NULL DEFAULT '{"type":"rolling","max_surge":1,"max_unavailable":0}',
 ADD COLUMN created_by TEXT NOT NULL DEFAULT '';
ALTER TABLE deployments ADD CONSTRAINT deployment_strategy_type CHECK (strategy->>'type' IN ('rolling', 'blue-green', 'canary'));
CREATE TABLE deployment_promotions (
 id UUID PRIMARY KEY,
 deployment_id UUID NOT NULL UNIQUE REFERENCES deployments(id),
 actor TEXT NOT NULL,
 request_nonce TEXT NOT NULL UNIQUE,
 resource_uid TEXT NOT NULL,
 resource_version TEXT NOT NULL,
 binding JSONB NOT NULL,
 outcome TEXT NOT NULL DEFAULT 'claimed' CHECK (outcome IN ('claimed','submitted','uncertain')),
 approved_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 completed_at TIMESTAMPTZ
);
