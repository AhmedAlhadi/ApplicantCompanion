"""Task-based model routing (§3, §45).

Each logical task maps to a "provider:model" string from settings. If the
configured provider is not available (missing key / unreachable), the router
falls back to the deterministic mock provider and records the fallback so
agent executions stay auditable.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings, get_settings
from .base import LLMProvider
from .providers import (
    GeminiProvider,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
)

TASKS = (
    "extraction",
    "classification",
    "research",
    "scoring",
    "matching",
    "strategy",
    "cv_generation",
    "cover_letter",
    "ats",
)

PROVIDER_ORDER = ("openrouter", "openai", "gemini", "ollama", "mock")

_providers: dict[str, LLMProvider] = {}


def get_provider(name: str) -> LLMProvider:
    if name not in _providers:
        registry: dict[str, type[LLMProvider]] = {
            "openrouter": OpenRouterProvider,
            "openai": OpenAIProvider,
            "gemini": GeminiProvider,
            "ollama": OllamaProvider,
            "mock": MockProvider,
        }
        if name not in registry:
            raise ValueError(f"Unknown LLM provider: {name!r}")
        _providers[name] = registry[name]()
    return _providers[name]


@dataclass
class RoutedModel:
    provider: LLMProvider
    model: str
    requested: str
    fell_back: bool = False


def _task_setting(settings: Settings, task: str) -> str:
    return getattr(settings, f"llm_model_{task}", "mock:deterministic")


def route_task(task: str) -> RoutedModel:
    if task not in TASKS:
        raise ValueError(f"Unknown LLM task: {task!r}")
    settings = get_settings()
    spec = _task_setting(settings, task)
    provider_name, _, model = spec.partition(":")
    provider = get_provider(provider_name or "mock")
    if provider_name != "mock" and not provider.is_available():
        mock = get_provider("mock")
        return RoutedModel(provider=mock, model="deterministic", requested=spec, fell_back=True)
    return RoutedModel(provider=provider, model=model or "deterministic", requested=spec)


def routing_table() -> dict[str, str]:
    settings = get_settings()
    return {task: _task_setting(settings, task) for task in TASKS}


def provider_status() -> dict[str, dict]:
    settings = get_settings()
    out = {}
    for name in PROVIDER_ORDER:
        provider = get_provider(name)
        out[name] = {
            "available": provider.is_available(),
            "configured": bool(
                (name == "openrouter" and settings.openrouter_api_key)
                or (name == "openai" and settings.openai_api_key)
                or (name == "gemini" and settings.gemini_api_key)
                or name in ("ollama", "mock")
            ),
        }
    return out
