"""Job Analysis Agent (§10-11): parses a JD into structured requirements."""
from __future__ import annotations

from typing import Any

from ..schemas.agents import JDAnalysisResult
from ..security.injection import sanitize_untrusted
from .base import AgentError, BaseAgent


class JobAnalysisAgent(BaseAgent):
    name = "job_analysis"
    task = "extraction"
    prompt_name = "jd_analysis"
    output_model = JDAnalysisResult
    validation_retries = 2
    max_tokens = 8192

    def build_user_message(self, *, jd_text: str, profession_context: str = "", **_) -> str:
        safe_jd = sanitize_untrusted(jd_text)
        return self.prompt.render_user(
            jd_text=safe_jd,
            payload_json="{}",
            profession_context=profession_context or "none provided",
        )

    def _parse(self, payload: dict | None) -> Any:
        result = super()._parse(payload)
        if not getattr(result, "requirements", None):
            raise AgentError(
                "JD analysis returned no requirements. Extract every stated "
                "qualification, skill, education, language, and experience item "
                "into the requirements array; do not leave it empty."
            )
        return result


class RequirementsExtractionAgent(JobAnalysisAgent):
    """Alias kept for architectural clarity (§5): requirement extraction is a
    specialization of JD analysis sharing the same prompt family."""

    name = "requirements_extraction"
