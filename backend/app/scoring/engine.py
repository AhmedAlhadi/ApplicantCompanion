"""Job-fit scoring engine (§18-21).

Scores are CALCULATED PROGRAMMATICALLY from structured RequirementMatch data —
the LLM only supplies the qualitative narrative. Weights are configurable.

Overall Fit = Σ(category_weight × category_score)
category_score = importance-weighted mean of requirement scores in that category
requirement score: MATCHED=1.0, TRANSFERABLE=0.5, NOT_MATCHED=0.0,
PARTIALLY_MATCHED=0.3–0.7 scaled by match confidence (§15).

UNKNOWN requirements (insufficient evidence to evaluate) are excluded from the
point estimate but are NOT silently dropped: the engine also returns a score
RANGE — overall_score_low treats every unknown as failed, overall_score_high
treats every unknown as fully matched — plus an importance-weighted `coverage`
ratio so the UI can communicate how much of the JD was actually evaluated.
"""
from __future__ import annotations

from ..models import JobRequirement, RequirementMatch
from ..qualification import resolve_match_status

DEFAULT_WEIGHTS: dict[str, float] = {
    "mandatory_qualifications": 0.25,
    "relevant_experience": 0.20,
    "technical_skills": 0.15,
    "responsibilities": 0.15,
    "domain_knowledge": 0.10,
    "leadership_management": 0.05,
    "education_certifications": 0.05,
    "language_other": 0.05,
}

WEIGHT_ALIASES = {
    "skills_and_tools": "technical_skills",
    "skill_or_tool": "technical_skills",
}


def normalize_weights(weights: dict[str, float] | None) -> dict[str, float]:
    raw = dict(weights or DEFAULT_WEIGHTS)
    out: dict[str, float] = {}
    for key, value in raw.items():
        out[WEIGHT_ALIASES.get(key, key)] = value
    for key, value in DEFAULT_WEIGHTS.items():
        out.setdefault(key, value)
    return out


STATUS_SCORES = {
    "MATCHED": 1.0,
    "TRANSFERABLE": 0.5,
    "NOT_MATCHED": 0.0,
}

# Partial credit scales with the matcher's confidence: a tentative partial is
# worth less than a well-evidenced one (centered on the historical 0.6).
PARTIAL_FLOOR = 0.3
PARTIAL_SPAN = 0.4  # PARTIALLY_MATCHED ∈ [0.3, 0.7]

IMPORTANCE_WEIGHTS = {"CRITICAL": 4.0, "HIGH": 3.0, "MEDIUM": 2.0, "LOW": 1.0}

UNVERIFIED_STATUSES = frozenset({"unverified", "needs_review"})


def _evidence_status(item: dict) -> str:
    return str(item.get("verification_status") or item.get("source") or "").strip().lower()


def unverified_evidence_summary(matches: list[RequirementMatch] | list[dict]) -> dict[str, int]:
    """Count cited evidence that is stored but not user-verified."""
    evidence_count = 0
    match_count = 0
    for match in matches:
        items = match.evidence if hasattr(match, "evidence") else match.get("evidence") or []
        unverified = [
            item for item in items
            if isinstance(item, dict) and _evidence_status(item) in UNVERIFIED_STATUSES
        ]
        if unverified:
            match_count += 1
            evidence_count += len(unverified)
    return {
        "unverified_evidence_count": evidence_count,
        "unverified_match_count": match_count,
    }


# JobRequirement.category -> scoring category
CATEGORY_MAP = {
    "education": "education_certifications",
    "certification": "education_certifications",
    "experience": "relevant_experience",
    "technical_skill": "technical_skills",
    "skill_or_tool": "technical_skills",
    "tool": "technical_skills",
    "clinical": "technical_skills",
    "methodology": "technical_skills",
    "functional": "mandatory_qualifications",
    "domain": "domain_knowledge",
    "language": "language_other",
    "management": "leadership_management",
    "responsibility": "responsibilities",
    "competency": "mandatory_qualifications",
    "other": "mandatory_qualifications",
}


def _scoring_category(req: JobRequirement) -> str:
    base = CATEGORY_MAP.get(req.category, "mandatory_qualifications")
    # Mandatory functional/competency requirements count as mandatory qualifications
    if req.requirement_type == "mandatory" and base == "mandatory_qualifications":
        return "mandatory_qualifications"
    return base


def _status_score(status: str, confidence: float) -> float:
    if status == "PARTIALLY_MATCHED":
        conf = min(max(confidence or 0.0, 0.0), 1.0)
        return PARTIAL_FLOOR + PARTIAL_SPAN * conf
    return STATUS_SCORES.get(status, 0.0)


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _combine(
    buckets: dict[str, list[tuple[float, float]]],
    weights: dict[str, float],
    *,
    unknown_weight_by_category: dict[str, float] | None = None,
    unknown_score: float | None = None,
) -> tuple[float, dict[str, float]]:
    """Weighted overall score + per-category scores.

    When ``unknown_score`` is given, unknown requirements are included in their
    category at that score (used for the pessimistic/optimistic bounds);
    otherwise categories with no evaluated requirements are excluded and the
    category weights are renormalized over the active categories.
    """
    category_scores: dict[str, float] = {}
    for category in weights:
        items = list(buckets.get(category, []))
        if unknown_score is not None and unknown_weight_by_category:
            items += [(unknown_score, w) for w in unknown_weight_by_category.get(category, [])]
        if not items:
            # No requirements in this category: neutral — redistribute by
            # marking as None and renormalizing weights below.
            category_scores[category] = -1.0
            continue
        total_w = sum(w for _, w in items)
        category_scores[category] = sum(s * w for s, w in items) / total_w

    active = {c: s for c, s in category_scores.items() if s >= 0}
    weight_sum = sum(weights.get(c, 0.0) for c in active) or 1.0
    overall = sum(active[c] * weights.get(c, 0.0) for c in active) / weight_sum
    return _clamp01(overall), {c: round(s, 4) for c, s in category_scores.items() if s >= 0}


def compute_score(
    requirements: list[JobRequirement],
    matches: list[RequirementMatch],
    *,
    weights: dict[str, float] | None = None,
    threshold: float = 0.80,
) -> dict:
    weights = normalize_weights(weights)
    match_by_req = {m.requirement_id: m for m in matches}

    buckets: dict[str, list[tuple[float, float]]] = {k: [] for k in weights}
    unknown_weight_by_category: dict[str, list[float]] = {}
    unknown_count = 0
    total_importance_weight = 0.0
    evaluated_importance_weight = 0.0
    strong, partial, gaps, transferable = [], [], [], []

    for req in requirements:
        match = match_by_req.get(req.id)
        status = match.status if match else "UNKNOWN"
        evaluation = getattr(match, "qualification_evaluation", None) if match else None
        status = resolve_match_status(evaluation, status)
        imp_w = IMPORTANCE_WEIGHTS.get(req.importance, 2.0)
        if req.requirement_type == "preferred":
            imp_w *= 0.5
        total_importance_weight += imp_w
        if status == "UNKNOWN":
            unknown_count += 1
            unknown_weight_by_category.setdefault(_scoring_category(req), []).append(imp_w)
            continue
        evaluated_importance_weight += imp_w
        score = _status_score(status, match.confidence if match else 0.0)
        bucket = _scoring_category(req)
        buckets.setdefault(bucket, []).append((score, imp_w))

        if status == "MATCHED":
            strong.append(req.text)
        elif status == "PARTIALLY_MATCHED":
            partial.append(req.text)
        elif status == "TRANSFERABLE":
            transferable.append(req.text)
        elif (
            status == "NOT_MATCHED"
            and req.requirement_type == "mandatory"
            and req.importance in ("CRITICAL", "HIGH")
        ):
            gaps.append(req.text)

    # Point estimate: unknowns excluded (renormalized); bounds: unknowns
    # counted as fully failed / fully matched.
    overall, category_scores = _combine(buckets, weights)
    overall_low, _ = _combine(
        buckets, weights,
        unknown_weight_by_category=unknown_weight_by_category, unknown_score=0.0,
    )
    overall_high, _ = _combine(
        buckets, weights,
        unknown_weight_by_category=unknown_weight_by_category, unknown_score=1.0,
    )
    coverage = (
        evaluated_importance_weight / total_importance_weight
        if total_importance_weight > 0
        else 0.0
    )

    return {
        "overall_score": round(overall, 4),
        "overall_score_low": round(min(overall_low, overall), 4),
        "overall_score_high": round(max(overall_high, overall), 4),
        "coverage": round(coverage, 4),
        "category_scores": category_scores,
        "weights": weights,
        "threshold": threshold,
        "recommendation": "strong_fit" if overall >= threshold else "below_threshold",
        "unknown_count": unknown_count,
        "strong_matches": strong,
        "partial_matches": partial,
        "gaps": gaps,
        "transferable": transferable,
        **unverified_evidence_summary(matches),
    }
