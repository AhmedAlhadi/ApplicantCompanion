"""Scoring engine tests with the deterministic fixtures of §56.

Covers: clearly qualifies / partially qualifies / lacks mandatory requirement /
transferable experience / no evidence — plus stability (same input, same score)
and configurability of weights (§18).
"""
from __future__ import annotations

from app.models import JobRequirement, RequirementMatch
from app.scoring.engine import DEFAULT_WEIGHTS, compute_score


def _req(text: str, category="functional", req_type="mandatory", importance="HIGH") -> JobRequirement:
    return JobRequirement(
        job_id="job-1", text=text, category=category,
        requirement_type=req_type, importance=importance, keywords=[],
        id=f"req-{abs(hash(text)) % 10**6}",
    )


def _match(req: JobRequirement, status: str, confidence: float = 0.9) -> RequirementMatch:
    return RequirementMatch(
        job_id="job-1", requirement_id=req.id, status=status,
        confidence=confidence, explanation="", match_kind="direct", evidence=[],
    )


def test_candidate_clearly_qualifies():
    reqs = [
        _req("5 years of Python experience", "technical_skill", importance="CRITICAL"),
        _req("Master's degree in Computer Science", "education", importance="HIGH"),
        _req("Power BI dashboards", "technical_skill"),
    ]
    matches = [_match(r, "MATCHED") for r in reqs]
    result = compute_score(reqs, matches)
    assert result["overall_score"] == 1.0
    assert result["recommendation"] == "strong_fit"
    assert len(result["strong_matches"]) == 3


def test_candidate_partially_qualifies():
    reqs = [
        _req("5 years of Python experience", "technical_skill", importance="CRITICAL"),
        _req("Master's degree in Computer Science", "education"),
        _req("Power BI dashboards", "technical_skill"),
        _req("French fluency", "language", req_type="preferred", importance="LOW"),
    ]
    matches = [
        _match(reqs[0], "MATCHED"),
        _match(reqs[1], "PARTIALLY_MATCHED"),
        _match(reqs[2], "PARTIALLY_MATCHED"),
        _match(reqs[3], "NOT_MATCHED"),
    ]
    result = compute_score(reqs, matches)
    assert 0.4 < result["overall_score"] < 0.9
    assert result["recommendation"] == "below_threshold"
    assert result["partial_matches"]


def test_candidate_lacks_mandatory_requirement():
    reqs = [
        _req("Master's degree in Computer Science", "education", importance="CRITICAL"),
        _req("5 years of Python experience", "technical_skill", importance="CRITICAL"),
    ]
    matches = [_match(reqs[0], "NOT_MATCHED"), _match(reqs[1], "MATCHED")]
    result = compute_score(reqs, matches)
    assert result["overall_score"] < 0.8
    assert "Master's degree in Computer Science" in result["gaps"]


def test_candidate_transferable_experience():
    reqs = [_req("AI product management experience", "experience", importance="HIGH")]
    matches = [_match(reqs[0], "TRANSFERABLE")]
    matches[0].match_kind = "transferable"
    result = compute_score(reqs, matches)
    assert result["overall_score"] == 0.5
    assert result["transferable"] == ["AI product management experience"]
    # Transferable must never score as a direct match
    assert result["strong_matches"] == []


def test_candidate_no_evidence_is_unknown_not_failed():
    reqs = [_req("Kubernetes administration", "technical_skill")]
    matches = [_match(reqs[0], "UNKNOWN", confidence=0.0)]
    result = compute_score(reqs, matches)
    # UNKNOWN is excluded from the denominator, not treated as failure (§15)
    assert result["unknown_count"] == 1
    assert result["category_scores"] == {}


def test_scoring_is_stable():
    reqs = [
        _req("Python", "technical_skill", importance="CRITICAL"),
        _req("Leadership", "management"),
    ]
    matches = [_match(reqs[0], "MATCHED"), _match(reqs[1], "PARTIALLY_MATCHED")]
    first = compute_score(reqs, matches)
    second = compute_score(reqs, matches)
    assert first == second


def test_weights_are_configurable():
    reqs = [
        _req("Python", "technical_skill", importance="CRITICAL"),
        _req("Master's degree", "education", importance="CRITICAL"),
    ]
    matches = [_match(reqs[0], "NOT_MATCHED"), _match(reqs[1], "MATCHED")]
    tech_heavy = compute_score(reqs, matches, weights={**DEFAULT_WEIGHTS, "technical_skills": 0.9, "education_certifications": 0.1})
    edu_heavy = compute_score(reqs, matches, weights={**DEFAULT_WEIGHTS, "technical_skills": 0.1, "education_certifications": 0.9})
    assert edu_heavy["overall_score"] > tech_heavy["overall_score"]
