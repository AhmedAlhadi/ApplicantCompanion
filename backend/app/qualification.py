"""Deterministic evaluation of structured qualification alternatives."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

DEGREE_LEVELS = {
    "secondary school": 1,
    "secondary education": 1,
    "high school diploma": 1,
    "secondary": 1,
    "high school": 1,
    "associate": 2,
    "diploma": 2,
    "first-level university": 3,
    "first level university": 3,
    "first university degree": 3,
    "university degree": 3,
    "bachelor": 3,
    "undergraduate": 3,
    "advanced university": 4,
    "advanced degree": 4,
    "master": 4,
    "mba": 4,
    "doctorate": 5,
    "doctoral": 5,
    "phd": 5,
    "ثانوية عامة": 1,
    "الثانوية العامة": 1,
    "ثانوية": 1,
    "الثانوية": 1,
    "ثانوي": 1,
    "توجيهي": 1,
    "دبلوم": 2,
    "ليسانس": 3,
    "بكالوريوس": 3,
    "البكالوريوس": 3,
    "ماجستير": 4,
    "الماجستير": 4,
    "دكتوراه": 5,
    "الدكتوراه": 5,
}


def degree_level(value: str) -> int:
    lowered = (value or "").lower().replace("’", "'")
    ranks = []
    for name, rank in DEGREE_LEVELS.items():
        if name not in lowered:
            continue
        # Generic "diploma" must not outrank an explicit secondary/high-school phrase.
        if name == "diploma" and ("high school" in lowered or "secondary" in lowered):
            continue
        if name == "دبلوم" and ("ثانوي" in lowered or "توجيهي" in lowered):
            continue
        ranks.append(rank)
    return max(ranks, default=0)


def _month(value: str | None, *, end: bool, as_of: date) -> int | None:
    if not value:
        return as_of.year * 12 + as_of.month if end else None
    match = re.search(r"(\d{4})(?:[-/](\d{1,2}))?", str(value))
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or (12 if end else 1))
    if not 1 <= month <= 12:
        return None
    return year * 12 + month


def overlapping_experience_years(
    experiences: list[dict[str, Any]],
    *,
    terms: list[str] | None = None,
    as_of: date | None = None,
) -> tuple[float, list[str]]:
    """Return union duration, avoiding double-counting overlapping roles."""
    as_of = as_of or date.today()
    wanted = [term.lower() for term in (terms or []) if term.strip()]
    intervals: list[tuple[int, int]] = []
    evidence_ids: list[str] = []
    for item in experiences:
        text = str(item.get("text") or "").lower()
        if wanted and not any(term in text for term in wanted):
            continue
        start = _month(item.get("start_date"), end=False, as_of=as_of)
        end = _month(item.get("end_date"), end=True, as_of=as_of)
        if start is None or end is None or end < start:
            continue
        # Half-open month interval; inclusive source dates become +1 month.
        intervals.append((start, end + 1))
        if item.get("entity_id"):
            evidence_ids.append(str(item["entity_id"]))
    if not intervals:
        return 0.0, []
    intervals.sort()
    merged: list[list[int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    months = sum(end - start for start, end in merged)
    return round(months / 12.0, 3), list(dict.fromkeys(evidence_ids))


def _text_match(value: str, terms: list[str]) -> bool:
    lowered = value.lower()
    return any(term.lower() in lowered for term in terms if term)


def _predicate_result(
    predicate: dict[str, Any],
    facts: dict[str, list[dict[str, Any]]],
    *,
    as_of: date,
) -> dict[str, Any]:
    kind = predicate.get("kind", "other")
    terms = [str(t) for t in predicate.get("terms", [])]
    value = str(predicate.get("value") or "")
    result: bool | None = None
    evidence_ids: list[str] = []
    actual: Any = None

    if kind == "degree_level":
        educations = facts.get("education", [])
        required = degree_level(str(predicate.get("minimum_level") or value))
        levels = [(degree_level(str(item.get("degree") or item.get("text") or "")), item) for item in educations]
        actual = max((level for level, _ in levels), default=0)
        if required and educations:
            result = actual >= required
            evidence_ids = [str(item.get("entity_id")) for level, item in levels if level == actual and item.get("entity_id")]
    elif kind == "relevant_experience":
        experiences = facts.get("experience", [])
        years, evidence_ids = overlapping_experience_years(experiences, terms=terms, as_of=as_of)
        actual = years
        minimum = predicate.get("minimum_years")
        if minimum is not None and experiences:
            result = years >= float(minimum)
    elif kind in {"education_field", "certification", "language", "skill"}:
        fact_key = {
            "education_field": "education",
            "certification": "certification",
            "language": "language",
            "skill": "skill",
        }[kind]
        candidates = facts.get(fact_key, [])
        wanted = terms or ([value] if value else [])
        matches = [
            item for item in candidates
            if _text_match(str(item.get("text") or " ".join(str(v) for v in item.values())), wanted)
        ]
        if candidates and wanted:
            result = bool(matches)
            evidence_ids = [str(item["entity_id"]) for item in matches if item.get("entity_id")]
        actual = len(matches)

    return {
        "predicate": predicate,
        "satisfied": result,
        "actual": actual,
        "evidence_ids": evidence_ids,
    }


def evaluate_qualification_paths(
    paths: list[dict[str, Any]],
    facts: dict[str, list[dict[str, Any]]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Evaluate ANY paths, where each path consists of ALL predicates."""
    if not paths:
        return {}
    as_of = as_of or date.today()
    path_results = []
    for index, path in enumerate(paths):
        predicates = [
            _predicate_result(predicate, facts, as_of=as_of)
            for predicate in path.get("predicates", [])
        ]
        values = [item["satisfied"] for item in predicates]
        if predicates and all(value is True for value in values):
            status = "MATCHED"
        elif any(value is False for value in values):
            status = "NOT_MATCHED"
        else:
            status = "UNKNOWN"
        path_results.append({
            "path_index": index,
            "label": path.get("label", ""),
            "status": status,
            "predicates": predicates,
        })

    statuses = [path["status"] for path in path_results]
    if "MATCHED" in statuses:
        status = "MATCHED"
        selected = statuses.index("MATCHED")
    elif statuses and all(item == "NOT_MATCHED" for item in statuses):
        status = "NOT_MATCHED"
        selected = None
    else:
        status = "UNKNOWN"
        selected = None
    evidence_ids = list(dict.fromkeys(
        evidence_id
        for path in path_results
        if path["status"] == "MATCHED"
        for predicate in path["predicates"]
        for evidence_id in predicate["evidence_ids"]
    ))
    return {
        "semantics": {"paths": "ANY", "predicates": "ALL"},
        "status": status,
        "selected_path_index": selected,
        "path_results": path_results,
        "evidence_ids": evidence_ids,
    }
