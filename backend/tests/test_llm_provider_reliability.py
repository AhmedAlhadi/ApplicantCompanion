"""Provider contract tests for strict schemas and bounded fallbacks."""
from __future__ import annotations

import json
from copy import deepcopy

import httpx

from app.llm.base import LLMRequest
from app.llm.providers import _openai_compatible_chat


def _response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status,
        text=json.dumps(payload),
        request=httpx.Request("POST", "https://example.test/chat/completions"),
    )


def test_openai_compatible_falls_back_when_strict_schema_is_unsupported(monkeypatch):
    calls: list[dict] = []
    responses = [
        _response(400, {"error": "json_schema unsupported"}),
        _response(200, {"choices": [{"message": {"content": '{"answer":"ok"}'}}], "usage": {}}),
    ]

    def fake_post(url, **kwargs):
        calls.append(deepcopy(kwargs["json"]))
        return responses.pop(0)

    monkeypatch.setattr("app.llm.providers.httpx.post", fake_post)
    result = _openai_compatible_chat(
        name="test",
        base_url="https://example.test",
        api_key="secret",
        model="model",
        request=LLMRequest(
            prompt_name="repair-test",
            prompt_version="v1",
            system="system",
            user="user",
            response_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        ),
    )

    assert result.data == {"answer": "ok"}
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[1]["response_format"] == {"type": "json_object"}


def test_openai_compatible_retries_transient_status(monkeypatch):
    calls = 0
    responses = [
        _response(503, {"error": "busy"}),
        _response(200, {"choices": [{"message": {"content": '{"answer":"ok"}'}}], "usage": {}}),
    ]

    def fake_post(url, **kwargs):
        nonlocal calls
        calls += 1
        return responses.pop(0)

    monkeypatch.setattr("app.llm.providers.httpx.post", fake_post)
    monkeypatch.setattr("app.llm.providers.time.sleep", lambda _: None)
    result = _openai_compatible_chat(
        name="test",
        base_url="https://example.test",
        api_key="secret",
        model="model",
        request=LLMRequest(
            prompt_name="retry-test",
            prompt_version="v1",
            system="system",
            user="user",
        ),
    )

    assert result.data == {"answer": "ok"}
    assert calls == 2
