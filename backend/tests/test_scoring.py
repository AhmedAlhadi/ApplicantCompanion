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
    # ...but the uncertainty is fully visible in the range and coverage
    assert result["overall_score_low"] == 0.0
    assert result["overall_score_high"] == 1.0
    assert result["coverage"] == 0.0
    assert result["unverified_evidence_count"] == 0


def test_unverified_evidence_is_counted_not_excluded():
    reqs = [_req("Power BI dashboards", "technical_skill")]
    match = _match(reqs[0], "MATCHED")
    match.evidence = [{
        "entity_type": "experience",
        "entity_id": "e1",
        "evidence": "Built Power BI dashboards",
        "source": "needs_review",
    }]
    result = compute_score(reqs, [match])
    assert result["overall_score"] == 1.0
    assert result["unverified_evidence_count"] == 1
    assert result["unverified_match_count"] == 1


def test_unknowns_produce_score_range():
    reqs = [
        _req("5 years of Python experience", "technical_skill", importance="HIGH"),
        _req("Kubernetes administration", "technical_skill", importance="HIGH"),
    ]
    matches = [_match(reqs[0], "MATCHED"), _match(reqs[1], "UNKNOWN", confidence=0.0)]
    result = compute_score(reqs, matches)
    # Point estimate only reflects the evaluated requirement
    assert result["overall_score"] == 1.0
    # Bounds show the best/worst case once the unknown is resolved
    assert result["overall_score_low"] == 0.5
    assert result["overall_score_high"] == 1.0
    assert result["coverage"] == 0.5
    assert result["unknown_count"] == 1


def test_bounds_collapse_when_everything_evaluated():
    reqs = [_req("Python", "technical_skill", importance="CRITICAL")]
    matches = [_match(reqs[0], "MATCHED")]
    result = compute_score(reqs, matches)
    assert result["overall_score_low"] == result["overall_score"] == result["overall_score_high"]
    assert result["coverage"] == 1.0


def test_partial_credit_scales_with_confidence():
    reqs = [_req("Power BI dashboards", "technical_skill")]
    weak = compute_score(reqs, [_match(reqs[0], "PARTIALLY_MATCHED", confidence=0.1)])
    strong = compute_score(reqs, [_match(reqs[0], "PARTIALLY_MATCHED", confidence=0.95)])
    assert weak["overall_score"] < 0.6 < strong["overall_score"]
    assert weak["overall_score"] < strong["overall_score"]


def test_overall_score_is_clamped_to_unit_interval():
    # Pathological (now rejected at the settings API, but the engine must be
    # safe anyway) negative weights could otherwise push the score above 1.
    reqs = [
        _req("Python", "technical_skill", importance="CRITICAL"),
        _req("Master's degree", "education", importance="CRITICAL"),
    ]
    matches = [_match(reqs[0], "MATCHED"), _match(reqs[1], "NOT_MATCHED")]
    result = compute_score(
        reqs, matches,
        weights={**DEFAULT_WEIGHTS, "technical_skills": 1.5, "education_certifications": -0.5},
    )
    assert 0.0 <= result["overall_score"] <= 1.0


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


def test_skills_and_tools_weight_alias():
    reqs = [_req("IV therapy", "skill_or_tool", importance="CRITICAL")]
    matches = [_match(reqs[0], "MATCHED")]
    aliased = compute_score(reqs, matches, weights={"skills_and_tools": 1.0})
    canonical = compute_score(reqs, matches, weights={"technical_skills": 1.0})
    assert aliased["overall_score"] == canonical["overall_score"] == 1.0
    assert "technical_skills" in aliased["category_scores"]


def test_failed_qualification_evaluation_does_not_wipe_matched_status():
    reqs = [_req("Digital transformation experience", "experience", importance="CRITICAL")]
    match = _match(reqs[0], "MATCHED")
    match.qualification_evaluation = {"status": "NOT_MATCHED"}
    result = compute_score(reqs, [match])
    assert result["overall_score"] == 1.0
    assert result["strong_matches"] == ["Digital transformation experience"]


def test_empty_requirements_have_zero_coverage():
    result = compute_score([], [])
    assert result["coverage"] == 0.0
    assert result["overall_score"] == 0.0

