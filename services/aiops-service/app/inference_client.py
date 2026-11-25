"""AIOps can send only approved aggregates to the isolated inference service."""
import json
import os
import urllib.request
from .inference_identity import sign_request
from .inference_security import approved_payload, validate_diagnosis


def infer_aggregates(raw: str):
    from .ai_provider import AIProviderResult
    try:
        payload=approved_payload(raw)
        body=json.dumps(payload,separators=(',',':')).encode()
        # Fixed in-cluster destination. TLS must use the service DNS SAN.
        url='https://ai-inference.cloudforge.svc.cluster.local:8443/v1/infer'
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        req=urllib.request.Request(url,data=body,method='POST',headers={
            'Content-Type':'application/json','X-CloudForge-Identity':sign_request(body)})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=8) as response:
            data=response.read(8193)
        if len(data)>8192: raise ValueError()
        value=json.loads(data)
        if value.get('status')!='success': raise ValueError()
        if value.get('provider')!='gemini' or value.get('model')!='gemini-2.5-flash': raise ValueError()
        diagnosis=validate_diagnosis(value['content'],payload['evidence'])
        return AIProviderResult('success','gemini','gemini-2.5-flash',diagnosis.model_dump_json())
    except Exception:
        return AIProviderResult('blocked','gemini','gemini-2.5-flash',None,
                                'Isolated inference unavailable, denied or budget exhausted')
