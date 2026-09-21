import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://cloudforge:cloudforge_password@localhost:5432/cloudforge",
)


@contextmanager
def get_connection() -> Iterator[Connection]:
    connection = psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    )

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
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
            ADD COLUMN IF NOT EXISTS root_cause_hints JSONB
            NOT NULL DEFAULT '[]'::jsonb
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

        print("AI-Ops database initialized successfully.")
