"""Career Coach Agent: retrieval-grounded answers with structured citations."""
from __future__ import annotations

import json

from ..schemas.agents import CoachAnswer
from ..security.injection import sanitize_untrusted
from .base import BaseAgent


class CareerCoachAgent(BaseAgent):
    name = "career_coach"
    task = "coach"
    prompt_name = "career_coach"
    output_model = CoachAnswer
    validation_retries = 1
    max_tokens = 2048

    def build_user_message(self, *, payload: dict, **_) -> str:
        safe = dict(payload)
        question = sanitize_untrusted(str(safe.get("question") or ""))
        safe["question"] = question
        return self.prompt.render_user(payload_json=json.dumps(safe, ensure_ascii=False))
