"""No tools, redirects, retries, paid fallback or free-text disclosure."""
import json
import os
import re
import urllib.request

from .inference_security import approved_payload, Diagnosis, validate_diagnosis


def analyze_gemini(provider, user_prompt):
    from .ai_provider import AIProviderResult
    model = provider.model or "gemini-2.5-flash"
    def rejected(reason):
        return AIProviderResult("blocked", "gemini", model, None, reason)
    if not provider.enabled:
        return rejected("External inference disabled by disclosure, terms or budget policy")
    if model != "gemini-2.5-flash":
        return rejected("Model unavailable or unapproved; no fallback")
    try:
        evidence = approved_payload(user_prompt)
        arn = os.environ["AI_GEMINI_SECRET_ARN"]
        if not re.fullmatch(r"arn:aws:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:cloudforge/[a-z0-9-]+/ai-inference/[A-Za-z0-9-]+", arn):
            return rejected("Dedicated inference secret required")
        if any(os.getenv(name) for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE")):
            return rejected("Workload identity required")
        import boto3
        from botocore.config import Config
        secret = boto3.client("secretsmanager", region_name=provider.aws_region,
                              config=Config(retries={"total_max_attempts": 1}, connect_timeout=1, read_timeout=2))
        key = json.loads(secret.get_secret_value(SecretId=arn)["SecretString"])
        if set(key) != {"api_key"} or not isinstance(key["api_key"], str) or not key["api_key"]:
            return rejected("Invalid dedicated inference secret")
        payload = {
            "systemInstruction": {"parts": [{"text": "Classify supplied evidence only. Cite zero-based evidence indices. Unknown evidence requires insufficient_evidence. No actions. Return JSON."}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(evidence)}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 512,
                                 "thinkingConfig": {"thinkingBudget": 0},
                                 "responseMimeType": "application/json",
                                 "responseJsonSchema": Diagnosis.model_json_schema()},
        }
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(payload).encode(), method="POST",
            headers={"x-goog-api-key": key["api_key"], "Content-Type": "application/json"})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=min(provider.timeout, 20)) as response:
            body = response.read(65537)
        if len(body) > 65536:
            return rejected("Provider response exceeds limit")
        candidate = json.loads(body)["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            return rejected("Incomplete or filtered provider response")
        parts = candidate["content"]["parts"]
        if len(parts) != 1 or set(parts[0]) != {"text"}:
            return rejected("Unexpected provider output")
        diagnosis = validate_diagnosis(parts[0]["text"], evidence["evidence"])
        return AIProviderResult("success", "gemini", model, diagnosis.model_dump_json())
    except Exception:
        return rejected("Inference unavailable or evidence rejected; no fallback")
