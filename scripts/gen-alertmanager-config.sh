#!/usr/bin/env bash
# =============================================================================
# CloudForge AI — Alertmanager config materialisation script
#
# Substitutes runtime SMTP credentials into alertmanager.yml, writing the
# result to alertmanager.generated.yml (which is .gitignored).
#
# Usage:
#   export ALERTMANAGER_SMTP_USER="you@example.com"
#   export ALERTMANAGER_SMTP_PASSWORD="your-smtp-app-password"
#   ./scripts/gen-alertmanager-config.sh
#
# The generated file is then mounted read-only into the alertmanager container.
# NEVER commit alertmanager.generated.yml to source control.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SRC="${REPO_ROOT}/monitoring/alertmanager/alertmanager.yml"
DST="${REPO_ROOT}/monitoring/alertmanager/alertmanager.generated.yml"

if [[ -z "${ALERTMANAGER_SMTP_USER:-}" ]]; then
  echo "ERROR: ALERTMANAGER_SMTP_USER must be set" >&2
  exit 1
fi

if [[ -z "${ALERTMANAGER_SMTP_PASSWORD:-}" ]]; then
  echo "ERROR: ALERTMANAGER_SMTP_PASSWORD must be set" >&2
  exit 1
fi

envsubst < "${SRC}" > "${DST}"
echo "Generated ${DST} (not committed to git)"
echo "Variables substituted: ALERTMANAGER_SMTP_USER, ALERTMANAGER_SMTP_PASSWORD"
