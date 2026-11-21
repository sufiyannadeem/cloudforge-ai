#!/usr/bin/env python3
"""Configure local CloudForge authentication without printing generated secrets."""
from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def read_env(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(".env is missing. Copy .env.example to .env and set POSTGRES_PASSWORD first.")
    lines = path.read_text(encoding="utf-8").splitlines()
    database_password = next(
        (line.partition("=")[2].strip() for line in lines if line.startswith("POSTGRES_PASSWORD=")),
        "",
    )
    if not database_password or "replace-with" in database_password.lower():
        raise SystemExit("Set a strong POSTGRES_PASSWORD in .env before bootstrapping authentication.")
    return lines


def get_value(lines: list[str], key: str) -> str:
    prefix = f"{key}="
    for line in reversed(lines):
        if line.startswith(prefix):
            return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


def set_value(lines: list[str], key: str, value: str) -> None:
    prefix = f"{key}="
    indices = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    replacement = f"{key}={value}"
    if indices:
        first = indices[0]
        lines[first] = replacement
        for index in reversed(indices[1:]):
            del lines[index]
    else:
        lines.append(replacement)


def main() -> None:
    lines = read_env(ENV_FILE)

    keys = (
        "CLOUDFORGE_FRONTEND_PROJECT_KEY", "CLOUDFORGE_FRONTEND_INFRASTRUCTURE_KEY",
        "CLOUDFORGE_FRONTEND_DEPLOYMENT_KEY", "CLOUDFORGE_FRONTEND_AIOPS_KEY",
        "CLOUDFORGE_FRONTEND_FINOPS_KEY", "CLOUDFORGE_AIOPS_DEPLOYMENT_KEY",
        "CLOUDFORGE_ALERTMANAGER_KEY", "CLOUDFORGE_SESSION_SECRET",
    )
    used = set()
    for key in keys:
        value = get_value(lines, key)
        if len(value.encode()) < 32 or "replace-with" in value.lower() or value in used:
            value = secrets.token_hex(32)
        used.add(value)
        set_value(lines, key, value)

    legacy_keys = {
        "CLOUDFORGE_AUTH_USERNAME", "CLOUDFORGE_AUTH_PASSWORD", "CLOUDFORGE_AUTH_ROLE",
        "CLOUDFORGE_INTERNAL_API_TOKEN", "CLOUDFORGE_REMEDIATION_IDENTITY_KEY",
    }
    lines = [line for line in lines if line.partition("=")[0] not in legacy_keys]

    if not get_value(lines, "CLOUDFORGE_AUTH_COOKIE_SECURE"):
        set_value(lines, "CLOUDFORGE_AUTH_COOKIE_SECURE", "false")

    payload = "\n".join(lines).rstrip() + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=".env.", dir=ROOT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, ENV_FILE)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    print("Local CloudForge authentication configured in .env (secrets were not printed).")
    print("Use the project-service account bootstrap command to create the first administrator.")
    print("For local HTTP, keep CLOUDFORGE_AUTH_COOKIE_SECURE=false. Use true behind HTTPS.")


if __name__ == "__main__":
    main()
