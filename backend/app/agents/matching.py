"""Candidate Matching Agent (§15-17) and strategy/CV/CL/ATS agents (§22-27)."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..schemas.agents import (
    ApplicationStrategyResult,
    ATSAnalysis,
    GeneratedCoverLetter,
    GeneratedCV,
    MatchingResult,
    ScoreNarrative,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)

# Leave headroom for system prompt, JSON schema, language block, and output tokens.
_MATCHING_USER_CHAR_BUDGET = 320_000
_EVIDENCE_TEXT_MAX = 600


def _truncate_text(value: Any, limit: int = _EVIDENCE_TEXT_MAX) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit]
    return value


def _trim_evidence_item(item: dict) -> dict:
    out = dict(item)
    if "text" in out:
        out["text"] = _truncate_text(out.get("text") or "")
    if "evidence" in out and isinstance(out["evidence"], str):
        out["evidence"] = _truncate_text(out["evidence"], 300)
    return out


def compact_matching_payload(
    *,
    requirements: list[dict],
    evidence: list[dict],
    evidence_by_requirement: dict[str, list[dict]],
    structured_facts: dict[str, list[dict]],
    char_budget: int = _MATCHING_USER_CHAR_BUDGET,
) -> dict[str, Any]:
    """Build a matching payload that fits a conservative context budget.

    Structured career facts are sent once (not per requirement). Per-requirement
    lists keep only retrieved evidence. Long text fields are truncated.
    """
    facts = {
        entity_type: [_trim_evidence_item(item) for item in items]
        for entity_type, items in (structured_facts or {}).items()
    }
    scoped = {
        req_id: [_trim_evidence_item(item) for item in items]
        for req_id, items in (evidence_by_requirement or {}).items()
    }
    unique = [_trim_evidence_item(item) for item in evidence]

    payload: dict[str, Any] = {
        "requirements": requirements,
        "evidence": unique,
        "evidence_by_requirement": scoped,
        "structured_facts": facts,
    }

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= char_budget:
        return payload

    logger.warning(
        "Matching payload oversized (%s chars); trimming evidence",
        len(encoded),
    )

    # Drop lowest-scored evidence per requirement first.
    for req_id, items in list(scoped.items()):
        ranked = sorted(
            items,
            key=lambda item: float(item.get("retrieval_score") or 0.0),
            reverse=True,
        )
        scoped[req_id] = ranked[:6]
    payload["evidence_by_requirement"] = scoped
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= char_budget:
        return payload

    # Shrink free-text further, then cap global evidence list.
    for collection in (facts.values(), scoped.values(), [unique]):
        for items in collection:
            for item in items:
                if isinstance(item.get("text"), str):
                    item["text"] = item["text"][:240]
    unique.sort(
        key=lambda item: float(item.get("retrieval_score") or 0.0),
        reverse=True,
    )
    payload["evidence"] = unique[:80]
    payload["evidence_by_requirement"] = scoped
    payload["structured_facts"] = facts

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > char_budget:
        logger.warning(
            "Matching payload still oversized after trim (%s chars)",
            len(encoded),
        )
    return payload


class CandidateMatchingAgent(BaseAgent):
    name = "candidate_matching"
    task = "matching"
    prompt_name = "candidate_matching"
    output_model = MatchingResult
    validation_retries = 2
    max_tokens = 8192

    def build_user_message(
        self,
        *,
        requirements: list[dict],
        evidence: list[dict],
        evidence_by_requirement: dict[str, list[dict]] | None = None,
        structured_facts: dict[str, list[dict]] | dict[str, dict[str, list[dict]]] | None = None,
        **_,
    ) -> str:
        # Accept legacy per-requirement structured_facts for mocks/tests, but
        # prefer a single shared career-facts object from the orchestrator.
        facts: dict[str, list[dict]] = _normalize_structured_facts(structured_facts or {})

        payload = compact_matching_payload(
            requirements=requirements,
            evidence=evidence,
            evidence_by_requirement=evidence_by_requirement or {},
            structured_facts=facts,
        )
        return self.prompt.render_user(
            payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )


def _normalize_structured_facts(facts: dict) -> dict[str, list[dict]]:
    """Normalize global or legacy per-requirement structured_facts."""
    if not facts:
        return {}
    sample = next(iter(facts.values()))
    # Global shape: {entity_type: [items]}
    if isinstance(sample, list):
        return {
            entity_type: [item for item in items if isinstance(item, dict)]
            for entity_type, items in facts.items()
            if isinstance(items, list)
        }
    # Legacy shape: {req_id: {entity_type: [items]}}
    if isinstance(sample, dict):
        merged: dict[str, dict[str, dict]] = {}
        for scoped in facts.values():
            if not isinstance(scoped, dict):
                continue
            for entity_type, items in scoped.items():
                if not isinstance(items, list):
                    continue
                bucket = merged.setdefault(entity_type, {})
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("entity_id") or item.get("text") or id(item))
                    bucket.setdefault(key, item)
        return {
            entity_type: list(items.values())
            for entity_type, items in merged.items()
        }
    return {}


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
        return self.prompt.render_user(payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


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
        return self.prompt.render_user(payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


class CVAgent(BaseAgent):
    name = "cv_generation"
    task = "cv_generation"
    prompt_name = "cv_generation"
    output_model = GeneratedCV
    validation_retries = 1
    max_tokens = 8192

    def build_user_message(self, **payload) -> str:
        return self.prompt.render_user(payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


class CoverLetterAgent(BaseAgent):
    name = "cover_letter_generation"
    task = "cover_letter"
    prompt_name = "cover_letter_generation"
    output_model = GeneratedCoverLetter
    validation_retries = 1
    max_tokens = 4096

    def build_user_message(self, **payload) -> str:
        return self.prompt.render_user(payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


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
        return self.prompt.render_user(payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
