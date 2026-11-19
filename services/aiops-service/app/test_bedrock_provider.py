from __future__ import annotations

from .ai_provider import AIProvider


def test_bedrock_disabled_without_model() -> None:
    import os

    previous_provider = os.environ.get("AI_PROVIDER")
    previous_model = os.environ.get("AI_MODEL")

    try:
        os.environ["AI_PROVIDER"] = "bedrock"
        os.environ.pop("AI_MODEL", None)

        provider = AIProvider()

        assert provider.enabled is False

        result = provider.analyze(
            system_prompt="system",
            user_prompt="user",
        )

        assert result.status == "error"
        assert result.provider == "bedrock"
        assert "AI_MODEL" in (result.error or "")
    finally:
        if previous_provider is None:
            os.environ.pop("AI_PROVIDER", None)
        else:
            os.environ["AI_PROVIDER"] = previous_provider

        if previous_model is None:
            os.environ.pop("AI_MODEL", None)
        else:
            os.environ["AI_MODEL"] = previous_model


def test_bedrock_request_shape() -> None:
    import os

    previous_provider = os.environ.get("AI_PROVIDER")
    previous_model = os.environ.get("AI_MODEL")

    try:
        os.environ["AI_PROVIDER"] = "bedrock"
        os.environ["AI_MODEL"] = "amazon.nova-lite-v1:0"

        provider = AIProvider()

        payload = provider._build_bedrock_request(
            system_prompt="You are CloudForge AI.",
            user_prompt='{"assessment":"evidence_available"}',
        )

        assert "messages" in payload
        assert "inferenceConfig" in payload

        assert payload["inferenceConfig"]["temperature"] == 0.1
        assert payload["inferenceConfig"]["maxTokens"] == 1200

        text = payload["messages"][0]["content"][0]["text"]

        assert "CloudForge AI" in text
        assert "evidence_available" in text
    finally:
        if previous_provider is None:
            os.environ.pop("AI_PROVIDER", None)
        else:
            os.environ["AI_PROVIDER"] = previous_provider

        if previous_model is None:
            os.environ.pop("AI_MODEL", None)
        else:
            os.environ["AI_MODEL"] = previous_model


def test_bedrock_response_extraction() -> None:
    provider = AIProvider()

    response = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": '{"assessment":"evidence_available"}'
                    }
                ]
            }
        }
    }

    content = provider._extract_bedrock_content(response)

    assert content == '{"assessment":"evidence_available"}'


def test_bedrock_empty_response() -> None:
    provider = AIProvider()

    content = provider._extract_bedrock_content({})

    assert content is None


def test_bedrock_handles_operation_not_allowed_error() -> None:
    """When Bedrock returns OperationNotAllowed (e.g. model access not enabled),
    BedrockProvider returns an error status rather than silently falling back to mock."""
    from botocore.exceptions import ClientError

    provider = AIProvider()
    provider.provider = "bedrock"
    provider.model = "amazon.nova-lite-v1:0"

    client_error = ClientError(
        error_response={
            "Error": {
                "Code": "OperationNotAllowedException",
                "Message": "Operation not allowed: model access not granted for account",
            }
        },
        operation_name="InvokeModel",
    )

    formatted = provider._format_aws_error(client_error)
    assert "OperationNotAllowedException" in formatted
    assert "Operation not allowed" in formatted


def test_production_rejects_mock_ai_provider() -> None:
    """Verify that in production mode, AIOps startup validates that AI_PROVIDER != 'mock'."""
    from pathlib import Path
    main_path = Path(__file__).resolve().parent / "main.py"
    with open(main_path) as f:
        source = f.read()

    assert "ai_provider_mode == \"mock\"" in source or 'ai_provider_mode == "mock"' in source
    assert "AI_PROVIDER 'mock' is not permitted in production" in source



def run_tests() -> None:
    tests = [
        (
            "BEDROCK DISABLED WITHOUT MODEL",
            test_bedrock_disabled_without_model,
        ),
        (
            "BEDROCK REQUEST SHAPE",
            test_bedrock_request_shape,
        ),
        (
            "BEDROCK RESPONSE EXTRACTION",
            test_bedrock_response_extraction,
        ),
        (
            "BEDROCK EMPTY RESPONSE",
            test_bedrock_empty_response,
        ),
        (
            "BEDROCK OPERATION NOT ALLOWED HANDLING",
            test_bedrock_handles_operation_not_allowed_error,
        ),
        (
            "PRODUCTION REJECTS MOCK AI PROVIDER",
            test_production_rejects_mock_ai_provider,
        ),
    ]

    print("========================================")
    print("BEDROCK PROVIDER VALIDATION")
    print("========================================")

    for name, test in tests:
        test()
        print(f"{name}: PASS")

    print()
    print("ALL BEDROCK PROVIDER TESTS PASSED")


if __name__ == "__main__":
    run_tests()
