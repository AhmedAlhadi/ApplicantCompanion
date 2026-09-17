"""Career Coach Agent: retrieval-grounded answers with structured citations."""
from __future__ import annotations

import json

from ..prompts.language import (
    conversational_output_language_block,
    reply_language_for_question,
    ui_language_for_user,
)
from ..schemas.agents import CoachAnswer
from ..security.injection import sanitize_untrusted
from .base import AgentContext, BaseAgent


class CareerCoachAgent(BaseAgent):
    name = "career_coach"
    task = "coach"
    prompt_name = "career_coach"
    output_model = CoachAnswer
    validation_retries = 1
    max_tokens = 2048

    def resolve_output_language(self, ctx: AgentContext, **kwargs) -> str:
        payload = kwargs.get("payload") or {}
        question = str(payload.get("question") or "")
        history = payload.get("history") or []
        fallback = ui_language_for_user(ctx.db, ctx.user_id)
        return reply_language_for_question(question, history, fallback)

    def output_language_instruction(self, language: str) -> str:
        return conversational_output_language_block(language)

    def build_user_message(self, *, payload: dict, **_) -> str:
        safe = dict(payload)
        question = sanitize_untrusted(str(safe.get("question") or ""))
        safe["question"] = question
        return self.prompt.render_user(payload_json=json.dumps(safe, ensure_ascii=False))
