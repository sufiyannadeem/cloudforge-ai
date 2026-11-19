#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PGPASSWORD
PGPASSWORD=$(docker exec cloudforge-postgres sh -c 'printf %s "$POSTGRES_PASSWORD"')
test -n "$PGPASSWORD"
schema="finops_audit_test_$(date +%s)_$$"
admin=(psql -h 127.0.0.1 -U cloudforge -d cloudforge -v ON_ERROR_STOP=1 -q)
"${admin[@]}" -c "CREATE SCHEMA $schema"
trap '"${admin[@]}" -c "DROP SCHEMA $schema CASCADE" >/dev/null' EXIT
{
    printf 'SET search_path=%s;\n' "$schema"
    cat services/project-service/internal/migration/migrations/005_finops_anomaly_audit.sql
} | "${admin[@]}"
export FINOPS_AUDIT_TEST_DATABASE_URL="host=127.0.0.1 user=cloudforge dbname=cloudforge sslmode=disable options='-c search_path=$schema'"
cd services/finops-service
.venv/bin/python -m pytest -q app/test_finops_anomaly_audit.py
