"""Career Knowledge Agent (§6-7): extraction + normalization + provenance."""
from __future__ import annotations

import json

from ..schemas.agents import CareerExtractionResult
from ..security.injection import sanitize_untrusted
from .base import BaseAgent


class CareerKnowledgeAgent(BaseAgent):
    name = "career_knowledge_extraction"
    task = "extraction"
    prompt_name = "career_extraction"
    output_model = CareerExtractionResult

    def build_user_message(self, *, document_text: str, document_name: str = "", **_) -> str:
        safe_text = sanitize_untrusted(document_text)
        return self.prompt.render_user(document_text=safe_text, document_name=document_name)


class CareerNormalizationAgent(BaseAgent):
    name = "career_normalization"
    task = "classification"
    prompt_name = "career_normalization"
    output_model = None  # validated manually (simple shape)

    def build_user_message(self, *, items: list[dict], **_) -> str:
        return self.prompt.render_user(payload_json=json.dumps({"items": items}))

    def _parse(self, payload):
        if payload is None or "canonical" not in payload:
            from .base import AgentError

            raise AgentError("Normalization output missing 'canonical'")
        return payload
