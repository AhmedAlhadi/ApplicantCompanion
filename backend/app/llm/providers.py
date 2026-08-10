"""Concrete LLM providers. All use plain HTTP via httpx — no vendor SDKs."""
from __future__ import annotations

import json

import httpx

from ..config import get_settings
from .base import LLMRequest, LLMResponse, LLMProvider

_TIMEOUT = 120.0


def _raise_http_error(resp: httpx.Response) -> None:
    detail = (resp.text or "")[:800]
    raise httpx.HTTPStatusError(
        f"{resp.status_code} for {resp.request.url}: {detail}",
        request=resp.request,
        response=resp,
    )


def _openai_compatible_chat(
    *,
    name: str,
    base_url: str,
    api_key: str,
    model: str,
    request: LLMRequest,
    extra_headers: dict[str, str] | None = None,
) -> LLMResponse:
    """Shared OpenAI-compatible /chat/completions call (OpenAI, OpenRouter, …)."""
    payload: dict = {
        "model": model,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }
    
    system_prompt = request.system
    if request.response_schema:
        payload["response_format"] = {"type": "json_object"}
        schema_json = json.dumps(request.response_schema, indent=2)
        system_prompt += f"\n\nIMPORTANT: You must return a JSON object that strictly adheres to the following JSON schema:\n```json\n{schema_json}\n```"

    payload["messages"] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.user},
    ]

    headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}
    url = f"{base_url.rstrip('/')}/chat/completions"
    resp = httpx.post(url, headers=headers, json=payload, timeout=_TIMEOUT)

    if resp.status_code >= 400:
        _raise_http_error(resp)

    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return LLMResponse(
        text=text,
        data=LLMProvider.extract_json(text),
        model=model,
        provider=name,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )


class OpenRouterProvider(LLMProvider):
    """Primary LLM gateway via OpenRouter (OpenAI-compatible API)."""

    name = "openrouter"

    def is_available(self) -> bool:
        return bool(get_settings().openrouter_api_key)

    def generate(self, model: str, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        return _openai_compatible_chat(
            name=self.name,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=model,
            request=request,
            extra_headers={
                "HTTP-Referer": settings.openrouter_http_referer,
                "X-Title": settings.openrouter_app_title,
            },
        )


class OpenAIProvider(LLMProvider):
    name = "openai"

    def is_available(self) -> bool:
        return bool(get_settings().openai_api_key)

    def generate(self, model: str, request: LLMRequest) -> LLMResponse:
        settings = get_settings()
        return _openai_compatible_chat(
            name=self.name,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=model,
            request=request,
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
        
        system_prompt = request.system
        if request.response_schema:
            schema_json = json.dumps(request.response_schema, indent=2)
            system_prompt += f"\n\nIMPORTANT: You must return a JSON object that strictly adheres to the following JSON schema:\n```json\n{schema_json}\n```"
            
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
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
        
        system_prompt = request.system
        if request.response_schema:
            schema_json = json.dumps(request.response_schema, indent=2)
            system_prompt += f"\n\nIMPORTANT: You must return a JSON object that strictly adheres to the following JSON schema:\n```json\n{schema_json}\n```"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
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
