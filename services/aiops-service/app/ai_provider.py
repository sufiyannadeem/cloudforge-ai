from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class AIProviderResult:
    status: str
    provider: str
    model: str | None
    content: str | None
    error: str | None = None


class AIProvider:
    """
    Provider abstraction for CloudForge AI.

    Supported providers:

        disabled
        mock
        openai_compatible
        bedrock

    The provider abstraction deliberately keeps external
    model access behind a single interface.

    AI output is never trusted directly. The caller is
    responsible for parsing and validating the response
    through CloudForge guardrails.
    """

    def __init__(self) -> None:
        self.provider = os.getenv(
            "AI_PROVIDER",
            "disabled",
        ).strip().lower()

        self.base_url = os.getenv(
            "AI_BASE_URL",
            "",
        ).rstrip("/")

        self.api_key = os.getenv(
            "AI_API_KEY",
            "",
        )

        self.model = os.getenv(
            "AI_MODEL",
            "",
        )

        self.aws_region = os.getenv(
            "AWS_REGION",
            os.getenv(
                "AWS_DEFAULT_REGION",
                "eu-west-1",
            ),
        ).strip()

        self.timeout = float(
            os.getenv(
                "AI_TIMEOUT_SECONDS",
                "20",
            )
        )

    @property
    def enabled(self) -> bool:
        """
        Returns True when an AI provider is explicitly enabled.

        Mock mode does not require credentials.

        Bedrock uses the AWS SDK credential chain and therefore
        does not require an API key in the application.
        """

        if self.provider == "mock":
            return True

        if self.provider == "bedrock":
            return bool(self.model)

        return (
            self.provider == "openai_compatible"
            and bool(self.base_url)
            and bool(self.api_key)
            and bool(self.model)
        )

    def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        """
        Execute the configured AI provider.
        """

        if self.provider == "disabled":
            return AIProviderResult(
                status="disabled",
                provider="disabled",
                model=None,
                content=None,
                error=None,
            )

        if self.provider == "mock":
            return self._analyze_mock(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        if self.provider == "bedrock":
            return self._analyze_bedrock(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        if self.provider == "openai_compatible":
            if not self.enabled:
                return AIProviderResult(
                    status="error",
                    provider=self.provider,
                    model=self.model or None,
                    content=None,
                    error=(
                        "OpenAI-compatible AI provider "
                        "is not fully configured. "
                        "Required: AI_BASE_URL, "
                        "AI_API_KEY and AI_MODEL."
                    ),
                )

            return self._analyze_openai_compatible(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        return AIProviderResult(
            status="error",
            provider=self.provider,
            model=self.model or None,
            content=None,
            error=(
                f"Unsupported AI provider: "
                f"{self.provider}"
            ),
        )

    def _analyze_mock(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        """
        Execute the local mock provider.

        No network request is made.
        """

        try:
            from .mock_ai_provider import (
                MockAIProvider,
            )

            mock_provider = MockAIProvider()

            result = mock_provider.analyze(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            return AIProviderResult(
                status=result.status,
                provider="mock",
                model=result.model,
                content=result.content,
                error=result.error,
            )

        except Exception as exc:
            return AIProviderResult(
                status="error",
                provider="mock",
                model="cloudforge-mock-v1",
                content=None,
                error=(
                    "Mock AI provider error: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

    def _analyze_bedrock(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        """
        Execute an AWS Bedrock Runtime inference request.

        Credentials are resolved through the standard AWS SDK
        credential chain.

        The application never stores AWS credentials.
        """

        if not self.model:
            return AIProviderResult(
                status="error",
                provider="bedrock",
                model=None,
                content=None,
                error=(
                    "Bedrock AI provider requires "
                    "AI_MODEL."
                ),
            )

        try:
            import boto3
            from botocore.exceptions import (
                BotoCoreError,
                ClientError,
            )

            client = boto3.client(
                "bedrock-runtime",
                region_name=self.aws_region,
            )

            request_body = self._build_bedrock_request(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            response = client.invoke_model(
                modelId=self.model,
                body=json.dumps(
                    request_body
                ),
                contentType="application/json",
                accept="application/json",
            )

            response_body = response["body"].read()

            response_json = json.loads(
                response_body.decode("utf-8")
            )

            content = self._extract_bedrock_content(
                response_json
            )

            if not content:
                return AIProviderResult(
                    status="error",
                    provider="bedrock",
                    model=self.model,
                    content=None,
                    error=(
                        "Bedrock returned an empty "
                        "model response."
                    ),
                )

            return AIProviderResult(
                status="success",
                provider="bedrock",
                model=self.model,
                content=content,
                error=None,
            )

        except ClientError as exc:
            return AIProviderResult(
                status="error",
                provider="bedrock",
                model=self.model,
                content=None,
                error=self._format_aws_error(
                    exc
                ),
            )

        except BotoCoreError as exc:
            return AIProviderResult(
                status="error",
                provider="bedrock",
                model=self.model,
                content=None,
                error=(
                    "Bedrock AWS SDK error: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        except TimeoutError:
            return AIProviderResult(
                status="error",
                provider="bedrock",
                model=self.model,
                content=None,
                error=(
                    "Bedrock request timed out."
                ),
            )

        except json.JSONDecodeError as exc:
            return AIProviderResult(
                status="error",
                provider="bedrock",
                model=self.model,
                content=None,
                error=(
                    "Bedrock returned invalid JSON: "
                    f"{exc}"
                ),
            )

        except Exception as exc:
            return AIProviderResult(
                status="error",
                provider="bedrock",
                model=self.model,
                content=None,
                error=(
                    "Unexpected Bedrock provider "
                    "error: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

    def _build_bedrock_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        """
        Build the request payload.

        CloudForge keeps temperature low because the AI is
        interpreting operational evidence rather than
        generating creative content.

        This request shape targets Amazon Nova-style
        Bedrock models.
        """

        return {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                f"{system_prompt}\n\n"
                                f"{user_prompt}"
                            )
                        }
                    ],
                }
            ],
            "inferenceConfig": {
                "temperature": 0.1,
                "maxTokens": 1200,
            },
        }

    def _extract_bedrock_content(
        self,
        response_json: dict[str, Any],
    ) -> str | None:
        """
        Extract text from an Amazon Nova-style response.
        """

        output = response_json.get(
            "output",
            {},
        )

        message = output.get(
            "message",
            {},
        )

        content = message.get(
            "content",
            [],
        )

        if not isinstance(
            content,
            list,
        ):
            return None

        text_parts: list[str] = []

        for item in content:
            if not isinstance(
                item,
                dict,
            ):
                continue

            text = item.get("text")

            if text:
                text_parts.append(
                    str(text)
                )

        if not text_parts:
            return None

        return "\n".join(
            text_parts
        ).strip()

    @staticmethod
    def _format_aws_error(
        exc: Exception,
    ) -> str:
        """
        Convert an AWS SDK exception into a safe application
        error message.

        Secret material is never included deliberately.
        """

        response = getattr(
            exc,
            "response",
            {},
        )

        error = (
            response.get(
                "Error",
                {},
            )
            if isinstance(
                response,
                dict,
            )
            else {}
        )

        code = error.get(
            "Code",
            type(exc).__name__,
        )

        message = error.get(
            "Message",
            str(exc),
        )

        return (
            "Bedrock AWS error "
            f"{code}: {message}"
        )

    def _analyze_openai_compatible(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIProviderResult:
        """
        Call an OpenAI-compatible /chat/completions endpoint.
        """

        url = (
            f"{self.base_url}/chat/completions"
        )

        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }

        body = json.dumps(
            payload
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": (
                    f"Bearer {self.api_key}"
                ),
                "Content-Type": (
                    "application/json"
                ),
                "Accept": (
                    "application/json"
                ),
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                response_body = (
                    response.read()
                    .decode("utf-8")
                )

            response_json = json.loads(
                response_body
            )

            content = (
                response_json
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content")
            )

            if not content:
                return AIProviderResult(
                    status="error",
                    provider=self.provider,
                    model=self.model,
                    content=None,
                    error=(
                        "AI provider returned an "
                        "empty response."
                    ),
                )

            return AIProviderResult(
                status="success",
                provider=self.provider,
                model=self.model,
                content=str(content),
            )

        except urllib.error.HTTPError as exc:
            try:
                response_body = (
                    exc.read()
                    .decode("utf-8")
                )
            except Exception:
                response_body = ""

            return AIProviderResult(
                status="error",
                provider=self.provider,
                model=self.model,
                content=None,
                error=(
                    "AI provider HTTP error "
                    f"{exc.code}: "
                    f"{response_body[:500]}"
                ),
            )

        except urllib.error.URLError as exc:
            return AIProviderResult(
                status="error",
                provider=self.provider,
                model=self.model,
                content=None,
                error=(
                    "Unable to reach AI provider: "
                    f"{exc.reason}"
                ),
            )

        except TimeoutError:
            return AIProviderResult(
                status="error",
                provider=self.provider,
                model=self.model,
                content=None,
                error=(
                    "AI provider request timed out."
                ),
            )

        except json.JSONDecodeError:
            return AIProviderResult(
                status="error",
                provider=self.provider,
                model=self.model,
                content=None,
                error=(
                    "AI provider returned "
                    "invalid JSON."
                ),
            )

        except Exception as exc:
            return AIProviderResult(
                status="error",
                provider=self.provider,
                model=self.model,
                content=None,
                error=(
                    "Unexpected AI provider error: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )


ai_provider = AIProvider()
