#!/usr/bin/env python3
"""Configure local CloudForge operator auth without printing generated secrets."""
from __future__ import annotations

import getpass
import os
import re
import secrets
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._@-]{1,128}$")
PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,}$")
VALID_ROLES = {"viewer", "devops", "sre", "platform-engineer", "admin"}


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


def prompt_username(current: str) -> str:
    value = current
    while not USERNAME_PATTERN.fullmatch(value):
        value = input("CloudForge login username [operator]: ").strip() or "operator"
        if not USERNAME_PATTERN.fullmatch(value):
            print("Use 1–128 characters: letters, numbers, dot, underscore, @, or hyphen.")
    return value


def prompt_password(current: str) -> str:
    if PASSWORD_PATTERN.fullmatch(current) and "replace-with" not in current.lower():
        return current
    while True:
        value = getpass.getpass("CloudForge login password (24+ letters/numbers/_/-): ")
        if PASSWORD_PATTERN.fullmatch(value) and "replace-with" not in value.lower():
            confirmation = getpass.getpass("Confirm password: ")
            if secrets.compare_digest(value, confirmation):
                return value
            print("Passwords do not match.")
        else:
            print("Use at least 24 characters containing only letters, numbers, underscore, or hyphen.")


def main() -> None:
    lines = read_env(ENV_FILE)

    token = get_value(lines, "CLOUDFORGE_INTERNAL_API_TOKEN")
    if len(token) < 32 or "replace-with" in token.lower():
        token = secrets.token_hex(32)
    set_value(lines, "CLOUDFORGE_INTERNAL_API_TOKEN", token)

    session_secret = get_value(lines, "CLOUDFORGE_SESSION_SECRET")
    if len(session_secret) < 32 or "replace-with" in session_secret.lower() or secrets.compare_digest(session_secret, token):
        session_secret = secrets.token_hex(32)
    set_value(lines, "CLOUDFORGE_SESSION_SECRET", session_secret)

    username = prompt_username(get_value(lines, "CLOUDFORGE_AUTH_USERNAME"))
    password = prompt_password(get_value(lines, "CLOUDFORGE_AUTH_PASSWORD"))
    set_value(lines, "CLOUDFORGE_AUTH_USERNAME", username)
    set_value(lines, "CLOUDFORGE_AUTH_PASSWORD", password)

    current_role = get_value(lines, "CLOUDFORGE_AUTH_ROLE").lower()
    if current_role not in VALID_ROLES:
        current_role = "viewer"
    role = input(f"CloudForge role {sorted(VALID_ROLES)} [{current_role}]: ").strip().lower() or current_role
    if role not in VALID_ROLES:
        raise SystemExit("Invalid role. Choose viewer, devops, sre, platform-engineer, or admin.")
    set_value(lines, "CLOUDFORGE_AUTH_ROLE", role)

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
    print(f"Configured role: {role}")
    print("For local HTTP, keep CLOUDFORGE_AUTH_COOKIE_SECURE=false. Use true behind HTTPS.")


if __name__ == "__main__":
    main()
