"""Dedicated inference app. No imports of operational routes, stores or tools."""
import asyncio
import json
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .inference_identity import verify_request
from .inference_security import approved_payload
from .postgres_ledger import reserve_request

app=FastAPI(title='CloudForge isolated inference', docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/health')
async def health():
    return {'status':'ok'}


@app.post('/v1/infer')
async def infer(request: Request):
    # Bound actual streamed bytes, irrespective of Content-Length.
    body=bytearray()
    try:
        async with asyncio.timeout(2):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>2048:
                    return JSONResponse({'detail':'Request too large'},status_code=413)
    except TimeoutError:
        return JSONResponse({'detail':'Request timed out'},status_code=408)
    try:
        assertions=request.headers.getlist('X-CloudForge-Identity')
        if len(assertions)!=1:
            raise ValueError()
        claims=verify_request(assertions[0],bytes(body))
    except Exception:
        return JSONResponse({'detail':'Invalid inference identity'},status_code=401)
    try:
        payload=approved_payload(bytes(body).decode())
    except Exception:
        return JSONResponse({'detail':'Unapproved disclosure'},status_code=422)
    try:
        from .workload_policy import validate_workload
        validate_workload()
        if not reserve_request(claims['nonce'],claims['body'],claims['exp']):
            return JSONResponse({'status':'blocked','error':'Budget, rate, replay or migration gate denied'},status_code=429)
        from .ai_provider import AIProvider
        if os.getenv('AI_WORKLOAD')!='inference':
            raise ValueError()
        provider=AIProvider()
        provider.provider='gemini'
        result=provider.analyze('',json.dumps(payload))
        return {'status':result.status,'provider':result.provider,'model':result.model,
                'content':result.content,'error':result.error}
    except Exception:
        return JSONResponse({'status':'blocked','error':'Inference unavailable'},status_code=503)
