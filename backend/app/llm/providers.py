"""Concrete LLM providers. All use plain HTTP via httpx — no vendor SDKs."""
from __future__ import annotations

import json

import httpx

from ..config import get_settings
from .base import LLMRequest, LLMResponse, LLMProvider

_TIMEOUT = 120.0


class OpenAIProvider(LLMProvider):
    name = "openai"

    def is_available(self) -> bool:
        return bool(get_settings().openai_api_key)

    def generate(self, model: str, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        payload: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.prompt_name,
                    "schema": request.response_schema,
                    "strict": True,
                },
            }
        resp = httpx.post(
            f"{settings.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            data=self.extract_json(text),
            model=model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )


class GeminiProvider(LLMProvider):
    name = "gemini"

    def is_available(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def generate(self, model: str, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={settings.gemini_api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "responseMimeType": "application/json" if request.response_schema else "text/plain",
            },
        }
        resp = httpx.post(url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            part.get("text", "")
            for part in data["candidates"][0]["content"]["parts"]
        )
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            data=self.extract_json(text),
            model=model,
            provider=self.name,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
        )


class OllamaProvider(LLMProvider):
    name = "ollama"

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{get_settings().ollama_base_url}/api/tags", timeout=2.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def generate(self, model: str, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        if request.response_schema:
            payload["format"] = "json"
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/chat", json=payload, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["message"]["content"]
        return LLMResponse(
            text=text,
            data=self.extract_json(text),
            model=model,
            provider=self.name,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )


class MockProvider(LLMProvider):
    """Deterministic offline provider.

    Implements rule-based versions of every agent task so the full pipeline
    runs with zero external dependencies and tests are reproducible (§56).
    The heuristics double as a genuine offline mode, not just a stub.
    """

    name = "mock"

    def generate(self, model: str, request: LLMRequest) -> LLMResponse:
        from . import mock_logic

        result = mock_logic.dispatch(request.prompt_name, request.user)
        return LLMResponse(
            text=json.dumps(result),
            data=result,
            model=model or "deterministic",
            provider=self.name,
            prompt_tokens=len(request.system.split()) + len(request.user.split()),
            completion_tokens=len(json.dumps(result).split()),
        )
