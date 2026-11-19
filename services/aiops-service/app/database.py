import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row



def _require_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL must be set; passwordless database connections are not allowed"
        )
    return database_url


@contextmanager
def get_connection(*, connect_timeout: int = 0) -> Iterator[Connection]:
    connection = psycopg.connect(
        _require_database_url(),
        row_factory=dict_row,
        connect_timeout=connect_timeout,
    )

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def claim_telemetry_assertion(nonce: str, expiry: int) -> bool:
    with get_connection(connect_timeout=2) as connection:
        connection.execute("SET LOCAL statement_timeout = '2s'")
        connection.execute("DELETE FROM aiops_telemetry_nonces WHERE expires_at <= clock_timestamp()")
        result = connection.execute("""
            INSERT INTO aiops_telemetry_nonces (nonce, expires_at)
            SELECT %s, to_timestamp(%s) WHERE to_timestamp(%s) > clock_timestamp()
            ON CONFLICT DO NOTHING
        """, (nonce.lower(), expiry, expiry))
        return result.rowcount == 1


def initialize_database(*, migration: bool = False) -> None:
    if os.getenv("APP_ENV") == "production":
        if not migration:
            raise RuntimeError("Use the explicit migration command before runtime startup")
        from .service_identity import production_database
        production_database(_require_database_url(), "cf_migrator")
    with get_connection(connect_timeout=5) as connection:
        connection.execute("SET LOCAL lock_timeout = '60s'")
        connection.execute("SET LOCAL statement_timeout = '120s'")
        connection.execute("SELECT pg_advisory_xact_lock(719920526321)")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS aiops_telemetry_nonces (
                nonce TEXT PRIMARY KEY,
                expires_at TIMESTAMPTZ NOT NULL
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS aiops_telemetry_nonces_expiry
            ON aiops_telemetry_nonces(expires_at)
        """)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS aiops_incidents (
                id VARCHAR(64) PRIMARY KEY,
                fingerprint VARCHAR(64) NOT NULL UNIQUE,
                alert_name VARCHAR(255) NOT NULL,
                service VARCHAR(255) NOT NULL,
                severity VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                impact VARCHAR(32) NOT NULL DEFAULT 'unknown',
                confidence VARCHAR(32) NOT NULL DEFAULT 'low',
                analysis_version VARCHAR(32) NOT NULL DEFAULT '1.0',
                priority VARCHAR(8) NOT NULL DEFAULT 'P4',
                summary TEXT NOT NULL,
                probable_cause TEXT NOT NULL,
                root_cause_hints JSONB NOT NULL
                    DEFAULT '[]'::jsonb,
                recommended_actions JSONB NOT NULL
                    DEFAULT '[]'::jsonb,
                labels JSONB NOT NULL DEFAULT '{}'::jsonb,
                annotations JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                alert_count INTEGER NOT NULL DEFAULT 1,
                raw_alerts JSONB NOT NULL DEFAULT '[]'::jsonb
            )
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS impact VARCHAR(32)
            NOT NULL DEFAULT 'unknown'
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS confidence VARCHAR(32)
            NOT NULL DEFAULT 'low'
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS analysis_version VARCHAR(32)
            NOT NULL DEFAULT '1.0'
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS priority VARCHAR(8)
            NOT NULL DEFAULT 'P4'
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR(255)
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(255)
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ
            """
        )
        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ
            """
        )
        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(255)
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS resolution_notes TEXT
            """
        )
        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS root_cause_hints JSONB
            NOT NULL DEFAULT '[]'::jsonb
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_incidents
            ADD COLUMN IF NOT EXISTS ai_analysis JSONB
            NOT NULL DEFAULT '{}'::jsonb
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_aiops_incidents_status
            ON aiops_incidents (status)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_aiops_incidents_service
            ON aiops_incidents (service)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_aiops_incidents_updated_at
            ON aiops_incidents (updated_at DESC)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_aiops_incidents_impact
            ON aiops_incidents (impact)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_aiops_incidents_priority
            ON aiops_incidents (priority)
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS aiops_incident_events (
                id BIGSERIAL PRIMARY KEY,
                incident_id VARCHAR(64) NOT NULL
                    REFERENCES aiops_incidents(id)
                    ON DELETE CASCADE,
                event_type VARCHAR(64) NOT NULL,
                message TEXT NOT NULL,
                status VARCHAR(32),
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_aiops_incident_events_incident_id
            ON aiops_incident_events (incident_id)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_aiops_incident_events_created_at
            ON aiops_incident_events (created_at DESC)
            """
        )


        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS aiops_remediation_proposals (
                id VARCHAR(64) PRIMARY KEY,
                incident_id VARCHAR(64) NOT NULL
                    REFERENCES aiops_incidents(id)
                    ON DELETE CASCADE,
                action VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                policy_decision VARCHAR(32) NOT NULL,
                policy_reason TEXT NOT NULL,
                reason TEXT,
                target_deployment_id VARCHAR(128),
                proposed_by VARCHAR(255) NOT NULL,
                approved_by VARCHAR(255),
                rejected_by VARCHAR(255),
                rejection_reason TEXT,
                execution_requested_by VARCHAR(255),
                result JSONB NOT NULL DEFAULT '{}'::jsonb,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                approved_at TIMESTAMPTZ,
                rejected_at TIMESTAMPTZ,
                executed_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ,
                verification_started_at TIMESTAMPTZ,
                verified_at TIMESTAMPTZ,
                verification_result JSONB NOT NULL DEFAULT '{}'::jsonb,
                execution_idempotency_key VARCHAR(255)
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_aiops_remediation_incident_id
            ON aiops_remediation_proposals (incident_id)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_aiops_remediation_status
            ON aiops_remediation_proposals (status)
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_remediation_proposals
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_remediation_proposals
            ADD COLUMN IF NOT EXISTS verification_started_at TIMESTAMPTZ
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_remediation_proposals
            ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_remediation_proposals
            ADD COLUMN IF NOT EXISTS verification_result JSONB
            NOT NULL DEFAULT '{}'::jsonb
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_remediation_proposals
            ADD COLUMN IF NOT EXISTS execution_idempotency_key VARCHAR(255)
            """
        )

        connection.execute(
            """
            ALTER TABLE aiops_remediation_proposals
            ADD COLUMN IF NOT EXISTS approved_role VARCHAR(32),
            ADD COLUMN IF NOT EXISTS approved_environment VARCHAR(32),
            ADD COLUMN IF NOT EXISTS dispatch_token_hash VARCHAR(64),
            ADD COLUMN IF NOT EXISTS dispatch_consumed_at TIMESTAMPTZ
            """
        )

        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_aiops_remediation_execution_idempotency
            ON aiops_remediation_proposals (execution_idempotency_key)
            WHERE execution_idempotency_key IS NOT NULL
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_aiops_remediation_expires_at
            ON aiops_remediation_proposals (expires_at)
            WHERE expires_at IS NOT NULL
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_aiops_remediation_created_at
            ON aiops_remediation_proposals (created_at DESC)
            """
        )

        print("AI-Ops database initialized successfully.")


if __name__ == "__main__":
    initialize_database(migration=True)
