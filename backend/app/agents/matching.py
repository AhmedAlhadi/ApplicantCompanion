"""Candidate Matching Agent (§15-17) and strategy/CV/CL/ATS agents (§22-27)."""
from __future__ import annotations

import json

from ..schemas.agents import (
    ApplicationStrategyResult,
    ATSAnalysis,
    GeneratedCoverLetter,
    GeneratedCV,
    MatchingResult,
    ScoreNarrative,
)
from .base import BaseAgent


class CandidateMatchingAgent(BaseAgent):
    name = "candidate_matching"
    task = "matching"
    prompt_name = "candidate_matching"
    output_model = MatchingResult

    def build_user_message(self, *, requirements: list[dict], evidence: list[dict], **_) -> str:
        payload = {"requirements": requirements, "evidence": evidence}
        return self.prompt.render_user(payload_json=json.dumps(payload))


class ScoringNarrativeAgent(BaseAgent):
    """Produces ONLY the qualitative overlay; numbers come from the scoring
    engine (§18: the LLM never outputs the score)."""

    name = "scoring_narrative"
    task = "scoring"
    prompt_name = "scoring"
    output_model = ScoreNarrative

    def build_user_message(self, *, matches: list[dict], category_scores: dict, overall_score: float, **_) -> str:
        payload = {
            "matches": matches,
            "category_scores": category_scores,
            "overall_score": overall_score,
        }
        return self.prompt.render_user(payload_json=json.dumps(payload))


class ApplicationStrategyAgent(BaseAgent):
    name = "application_strategy"
    task = "strategy"
    prompt_name = "application_strategy"
    output_model = ApplicationStrategyResult

    def build_user_message(self, *, job_analysis: dict, matches: list[dict], score: dict, research: list[dict], profile_summary: str, **_) -> str:
        payload = {
            "job_analysis": job_analysis,
            "matches": matches,
            "score": score,
            "research": research,
            "profile_summary": profile_summary,
        }
        return self.prompt.render_user(payload_json=json.dumps(payload))


class CVAgent(BaseAgent):
    name = "cv_generation"
    task = "cv_generation"
    prompt_name = "cv_generation"
    output_model = GeneratedCV

    def build_user_message(self, **payload) -> str:
        return self.prompt.render_user(payload_json=json.dumps(payload))


class CoverLetterAgent(BaseAgent):
    name = "cover_letter_generation"
    task = "cover_letter"
    prompt_name = "cover_letter_generation"
    output_model = GeneratedCoverLetter

    def build_user_message(self, **payload) -> str:
        return self.prompt.render_user(payload_json=json.dumps(payload))


class ATSAnalysisAgent(BaseAgent):
    name = "ats_analysis"
    task = "ats"
    prompt_name = "ats_analysis"
    output_model = ATSAnalysis

    def build_user_message(self, *, document_text: str, keywords: list, requirements: list, **_) -> str:
        payload = {
            "document_text": document_text,
            "keywords": keywords,
            "requirements": requirements,
        }
        return self.prompt.render_user(payload_json=json.dumps(payload))
