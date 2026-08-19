"""Job-fit scoring engine (§18-21).

Scores are CALCULATED PROGRAMMATICALLY from structured RequirementMatch data —
the LLM only supplies the qualitative narrative. Weights are configurable.

Overall Fit = Σ(category_weight × category_score)
category_score = importance-weighted mean of requirement scores in that category
requirement score: MATCHED=1.0, PARTIALLY_MATCHED=0.6, TRANSFERABLE=0.5,
NOT_MATCHED=0.0, UNKNOWN excluded from the denominator (§15).
"""
from __future__ import annotations

from ..models import JobRequirement, RequirementMatch

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

STATUS_SCORES = {
    "MATCHED": 1.0,
    "PARTIALLY_MATCHED": 0.6,
    "TRANSFERABLE": 0.5,
    "NOT_MATCHED": 0.0,
}

IMPORTANCE_WEIGHTS = {"CRITICAL": 4.0, "HIGH": 3.0, "MEDIUM": 2.0, "LOW": 1.0}

# JobRequirement.category -> scoring category
CATEGORY_MAP = {
    "education": "education_certifications",
    "certification": "education_certifications",
    "experience": "relevant_experience",
    "technical_skill": "technical_skills",
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


def compute_score(
    requirements: list[JobRequirement],
    matches: list[RequirementMatch],
    *,
    weights: dict[str, float] | None = None,
    threshold: float = 0.80,
) -> dict:
    weights = dict(weights or DEFAULT_WEIGHTS)
    match_by_req = {m.requirement_id: m for m in matches}

    buckets: dict[str, list[tuple[float, float]]] = {k: [] for k in weights}
    unknown_count = 0
    strong, partial, gaps, transferable = [], [], [], []

    for req in requirements:
        match = match_by_req.get(req.id)
        status = match.status if match else "UNKNOWN"
        # A structured alternative group is one requirement: ANY qualifying
        # path earns one match, and unsatisfied paths are never double-counted.
        evaluation = getattr(match, "qualification_evaluation", None) if match else None
        if evaluation and evaluation.get("status") in {
            "MATCHED", "NOT_MATCHED", "UNKNOWN",
        }:
            status = evaluation["status"]
        imp_w = IMPORTANCE_WEIGHTS.get(req.importance, 2.0)
        if req.requirement_type == "preferred":
            imp_w *= 0.5
        if status == "UNKNOWN":
            unknown_count += 1
            continue
        score = STATUS_SCORES.get(status, 0.0)
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

    category_scores: dict[str, float] = {}
    for category, items in buckets.items():
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

    return {
        "overall_score": round(overall, 4),
        "category_scores": {c: round(s, 4) for c, s in category_scores.items() if s >= 0},
        "weights": weights,
        "threshold": threshold,
        "recommendation": "strong_fit" if overall >= threshold else "below_threshold",
        "unknown_count": unknown_count,
        "strong_matches": strong,
        "partial_matches": partial,
        "gaps": gaps,
        "transferable": transferable,
    }
