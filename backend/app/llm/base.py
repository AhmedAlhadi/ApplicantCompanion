"""LLM provider abstraction (§3 'AI abstraction').

The application never talks to a concrete vendor SDK. Providers are plain
HTTP clients selected by configuration, and tasks are routed to models via
settings — so extraction/classification can run on cheap models while CV
generation uses stronger ones (§45).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class LLMRequest(BaseModel):
    prompt_name: str
    prompt_version: str
    system: str
    user: str
    response_schema: dict[str, Any] | None = None  # JSON schema for structured output
    temperature: float = 0.2
    max_tokens: int = 4096


class LLMResponse(BaseModel):
    text: str
    data: dict[str, Any] | None = None  # parsed JSON payload
    model: str = ""
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def generate(self, model: str, request: LLMRequest) -> LLMResponse:
        """Synchronous generation (FastAPI runs handlers in a threadpool)."""

    def is_available(self) -> bool:
        return True

    @staticmethod
    def extract_json(text: str) -> dict[str, Any] | None:
        """Best-effort JSON extraction from a model response."""
        text = text.strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None
