import asyncio
import base64
import hmac
import json
import os
import time
from secrets import token_hex

import httpx2 as httpx


class SignedTestClient:
    """Sign the final request URL without performing network I/O."""

    def __init__(self, app):
        self.app = app

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def request(self, method, url, **kwargs):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://testserver",
            ) as client:
                request = client.build_request(method, url, **kwargs)
                role = request.headers.pop("X-Test-Human-Role", None)
                if role is not None:
                    now = int(time.time())
                    payload = base64.urlsafe_b64encode(json.dumps({
                        "iss": "frontend", "aud": "finops", "sub": "test-operator",
                        "role": role, "method": request.method,
                        "target": request.url.raw_path.decode("ascii"),
                        "iat": now, "exp": now + 25, "nonce": token_hex(16),
                    }).encode()).rstrip(b"=")
                    key = os.environ["CLOUDFORGE_FRONTEND_KEY"].encode()
                    signature = hmac.digest(key, payload, "sha256").hex()
                    request.headers["X-CloudForge-Identity"] = f"{payload.decode()}.{signature}"
                return await client.send(request)

        return asyncio.run(send())
