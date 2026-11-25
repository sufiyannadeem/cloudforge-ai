"""Body-bound, expiring internal assertion matching existing service identity format."""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from secrets import token_hex


def key_bytes():
    key = Path(os.environ['AI_INTERNAL_KEY_FILE']).read_bytes().strip()
    if len(key) < 32:
        raise ValueError('Internal identity unavailable')
    return key


def sign_request(body: bytes) -> str:
    now = int(time.time())
    claims = dict(iss='aiops', aud='inference', method='POST', target='/v1/infer',
                  iat=now, exp=now+25, nonce=token_hex(16), body=hashlib.sha256(body).hexdigest())
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=')
    return payload.decode()+'.'+hmac.digest(key_bytes(),payload,'sha256').hex()


def verify_request(assertion: str, body: bytes) -> dict:
    if len(assertion)>4096:
        raise ValueError('Invalid assertion')
    payload, sep, signature = assertion.partition('.')
    if not sep or not hmac.compare_digest(hmac.digest(key_bytes(),payload.encode(),'sha256').hex(),signature):
        raise ValueError('Invalid assertion')
    value=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
    now=int(time.time())
    if (value.get('iss')!='aiops' or value.get('aud')!='inference'
        or value.get('method')!='POST' or value.get('target')!='/v1/infer'
        or type(value.get('iat')) is not int or type(value.get('exp')) is not int
        or not now-30<=value['iat']<=now+5 or not now<value['exp']<=value['iat']+25
        or not re.fullmatch('[a-f0-9]{32}',value.get('nonce',''))
        or value.get('body')!=hashlib.sha256(body).hexdigest()):
        raise ValueError('Invalid assertion')
    return value
