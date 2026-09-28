"""Provider contract tests for strict schemas and bounded fallbacks."""
from __future__ import annotations

import json
from copy import deepcopy

import httpx

from app.llm.base import LLMRequest
from app.llm.json_schema import openai_strict_schema, schema_name
from app.llm.providers import _openai_compatible_chat
from app.schemas.agents import JDAnalysisResult, MatchingResult

_UNSUPPORTED_STRICT = {
    "default",
    "title",
    "minItems",
    "minLength",
    "minimum",
    "maximum",
    "pattern",
    "format",
}


def _assert_openai_strict(node, path="$"):
    if isinstance(node, list):
        for index, item in enumerate(node):
            _assert_openai_strict(item, f"{path}[{index}]")
        return
    if not isinstance(node, dict):
        return
    if "$ref" in node:
        assert set(node) == {"$ref"}, path
        return
    for key in _UNSUPPORTED_STRICT:
        assert key not in node, f"{path} still has {key}"
    if node.get("type") == "object" or "properties" in node:
        assert node.get("additionalProperties") is False, path
        assert list(node.get("properties") or {}) == list(node.get("required") or []), path
    for key, value in node.items():
        _assert_openai_strict(value, f"{path}.{key}")


def test_schema_name_is_openai_safe():
    assert schema_name("repair-test") == "repair-test"
    assert schema_name("jd_analysis") == "jd_analysis"
    assert schema_name("a/b c") == "a_b_c"


def test_agent_schemas_become_openai_strict():
    for model in (JDAnalysisResult, MatchingResult):
        schema = openai_strict_schema(model.model_json_schema())
        _assert_openai_strict(schema)
        assert schema["type"] == "object"
        assert "requirements" in schema["properties"] or "matches" in schema["properties"]


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
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    assert calls[0]["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert calls[0]["response_format"]["json_schema"]["schema"]["required"] == ["answer"]
    assert "default" not in json.dumps(calls[0]["response_format"]["json_schema"]["schema"])
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
