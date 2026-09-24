from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class AIProviderResult:
    status: str
    provider: str
    model: str | None
    content: str | None
    error: str | None = None


class AIProvider:
    """
    Provider abstraction for Incident Intelligence.

    Supported modes:

        AI_PROVIDER=disabled
        AI_PROVIDER=mock
        AI_PROVIDER=openai_compatible

    Mock provider:
        No external API call is made.

    OpenAI-compatible provider requires:

        AI_BASE_URL
        AI_API_KEY
        AI_MODEL
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

        OpenAI-compatible mode requires all required
        external-provider configuration.
        """

        if self.provider == "mock":
            return True

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

        if self.provider != "openai_compatible":
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
