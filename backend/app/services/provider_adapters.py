"""Provider adapters for direct OpenAI and OpenAI-compatible endpoints."""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import SecretStr

from app.models.provider import (
    GenerationProvenance,
    GenerationResult,
    ModelCapability,
    ModelDescriptor,
    ProviderType,
    StructuredGenerationRequest,
    TextGenerationRequest,
)
from app.services.llm_provider import NonTransientLLMError, TransientLLMError
from app.services.provider_ports import ProviderAdapter


class OpenAICompatibleAdapter(ProviderAdapter):
    """Small transport adapter for OpenAI-compatible chat-completions APIs."""

    provider_type = ProviderType.OPENAI_COMPATIBLE

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60,
        adapter_version: str = "1",
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if not model_id.strip():
            raise ValueError("model_id must not be blank")
        self._api_key = SecretStr(api_key)
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._adapter_version = adapter_version
        self.model_descriptor = ModelDescriptor(
            provider_type=self.provider_type,
            model_id=model_id,
            display_name=model_id,
            capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT},
            supports_json_schema=True,
        )

    def generate_text(self, request: TextGenerationRequest) -> GenerationResult:
        return self._generate(request.prompt, request.max_tokens, request.temperature, None)

    # Compatibility shim while domain services migrate to capability ports.
    def generate(self, prompt: str, *, max_tokens: int, temperature: float) -> str:
        return self.generate_text(
            TextGenerationRequest(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        ).content

    def generate_structured(self, request: StructuredGenerationRequest) -> GenerationResult:
        return self._generate(request.prompt, request.max_tokens, request.temperature, request.json_schema)

    def _generate(self, prompt: str, max_tokens: int, temperature: float, schema: dict[str, Any] | None) -> GenerationResult:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self.model_descriptor.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "paperscape_output", "schema": schema, "strict": True}}
        request = Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {408, 429, 500, 502, 503, 504}:
                raise TransientLLMError(f"Transient HTTP {exc.code}") from exc
            raise NonTransientLLMError(f"Provider HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            raise TransientLLMError("Provider network error") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise NonTransientLLMError("Provider returned invalid JSON") from exc

        try:
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise NonTransientLLMError("Provider response did not contain assistant content") from exc
        usage = body.get("usage") if isinstance(body, dict) else None
        return GenerationResult(
            content=content.strip(),
            provenance=GenerationProvenance(
                provider_type=self.provider_type,
                model_id=self.model_descriptor.model_id,
                adapter_version=self._adapter_version,
                latency_ms=round((time.perf_counter() - started) * 1000),
                input_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
                output_tokens=usage.get("completion_tokens") if isinstance(usage, dict) else None,
            ),
        )


class OpenAIAdapter(OpenAICompatibleAdapter):
    provider_type = ProviderType.OPENAI
