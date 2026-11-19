from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time

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
