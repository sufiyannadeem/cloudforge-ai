from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from secrets import token_hex
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from fastapi import HTTPException, Request


def frontend_identity(request: Request, audience: str) -> dict:
    key = os.getenv("CLOUDFORGE_FRONTEND_KEY", "")
    if len(key.encode()) < 32 or "replace-with" in key.lower():
        raise HTTPException(503, "Service identity is not configured")
    values = request.headers.getlist("X-CloudForge-Identity")
    if len(values) != 1 or len(values[0]) > 8192:
        raise HTTPException(401, "Service identity required")
    payload, _, signature = values[0].partition(".")
    expected = hmac.digest(key.encode(), payload.encode(), hashlib.sha256).hex()
    if not hmac.compare_digest(expected.encode(), signature.encode()):
        raise HTTPException(401, "Invalid service identity")
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        now = int(time.time())
        path = request.scope.get("raw_path", request.scope["path"].encode())
        query = request.scope.get("query_string", b"")
        target = (path + (b"?" + query if query else b"")).decode("ascii")
        if (
            claims["iss"] != "frontend" or claims["aud"] != audience
            or claims["method"] != request.method or claims["target"] != target
            or type(claims["iat"]) is not int or type(claims["exp"]) is not int
            or not now - 30 <= claims["iat"] <= now + 5
            or not now < claims["exp"] <= claims["iat"] + 30 or claims["exp"] <= claims["iat"]
            or not re.fullmatch(r"[0-9a-fA-F]{32}", claims["nonce"])
            or not re.fullmatch(r"[a-z0-9][a-z0-9._@-]{0,127}", claims["sub"])
            or claims["role"] not in {"platform-engineer", "sre", "developer"}
        ):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise HTTPException(401, "Invalid service identity") from None
    return claims


def deployment_identity(url: str, method: str) -> str:
    key = os.getenv("CLOUDFORGE_AIOPS_DEPLOYMENT_KEY", "")
    if len(key.encode()) < 32 or "replace-with" in key.lower() or key == os.getenv("CLOUDFORGE_FRONTEND_KEY"):
        raise RuntimeError("Deployment service identity is not configured")
    parsed = urlsplit(url)
    now = int(time.time())
    claims = {
        "iss": "aiops", "aud": "deployment", "method": method,
        "target": parsed.path + ("?" + parsed.query if parsed.query else ""),
        "iat": now, "exp": now + 25, "nonce": token_hex(16),
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    return payload.decode() + "." + hmac.digest(key.encode(), payload, hashlib.sha256).hex()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


open_deployment = build_opener(_NoRedirect()).open


def production_database(dsn: str, principal: str) -> None:
    """Reject shared identities, local sockets and unverifiable production TLS."""
    if os.getenv("APP_ENV") != "production":
        return
    from psycopg.conninfo import conninfo_to_dict
    try:
        config = conninfo_to_dict(dsn)
    except Exception:
        raise RuntimeError("Invalid production database configuration") from None
    host = config.get("host", "")
    if (config.get("user") != principal or config.get("sslmode") != "verify-full"
            or not host or host.startswith("/") or "," in host):
        raise RuntimeError("Production requires a dedicated database principal and hostname-verified TLS")
