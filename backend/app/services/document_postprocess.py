"""Post-generation fixes for CVs and cover letters."""
from __future__ import annotations

import re
from typing import Any

from ..evidence_citations import sanitize_prose_field

_SPACE_RE = re.compile(r"\s+")


def _norm(value: str | None) -> str:
    return _SPACE_RE.sub(" ", (value or "").strip().lower())


def _role_key(organization: str | None, job_title: str | None) -> tuple[str, str]:
    return (_norm(organization), _norm(job_title))


def _same_role(left_org: str | None, left_title: str | None, right_org: str | None, right_title: str | None) -> bool:
    if _role_key(left_org, left_title) == _role_key(right_org, right_title):
        return True
    if _norm(left_org) != _norm(right_org):
        return False
    left, right = _norm(left_title), _norm(right_title)
    return bool(left and right and (left in right or right in left))


_OPEN_ENDED = {"", "present", "current", "now", "ongoing"}


def _normalize_date(value: str | None, *, empty: str) -> str:
    raw = str(value or "").strip()
    if not raw or raw.lower() in _OPEN_ENDED:
        return empty
    return raw


def _date_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    """Newest start_date first; treat Present/empty end dates as open-ended."""
    start = _normalize_date(entry.get("start_date"), empty="0000-00")
    end = _normalize_date(entry.get("end_date"), empty="9999-12")
    return (start, end)


def relevance_terms(job: dict | None, strategy: dict | None, matches: list[dict] | None) -> set[str]:
    terms: set[str] = set()
    job = job or {}
    strategy = strategy or {}
    parsed = job.get("parsed") or {}
    for raw in parsed.get("keywords") or []:
        term = raw.get("term") if isinstance(raw, dict) else str(raw)
        if term:
            terms.add(str(term).lower())
    for req in parsed.get("requirements") or []:
        if isinstance(req, dict):
            for kw in req.get("keywords") or []:
                if kw:
                    terms.add(str(kw).lower())
            text = req.get("text") or ""
            if text:
                terms.update(w for w in re.findall(r"[a-zA-Z][a-zA-Z+\-]{3,}", text.lower()))
    for field in ("position_title",):
        value = job.get(field)
        if value:
            terms.update(w for w in re.findall(r"[a-zA-Z][a-zA-Z+\-]{3,}", str(value).lower()))
    for item in (strategy.get("keywords") or []) + (strategy.get("priority_skills") or []):
        if item:
            terms.add(str(item).lower())
    for match in matches or []:
        if match.get("status") in ("MATCHED", "PARTIALLY_MATCHED", "TRANSFERABLE"):
            req_text = match.get("requirement_text") or ""
            terms.update(w for w in re.findall(r"[a-zA-Z][a-zA-Z+\-]{3,}", req_text.lower()))
            for ev in match.get("evidence") or []:
                snippet = ev.get("evidence") if isinstance(ev, dict) else ""
                if snippet:
                    terms.update(w for w in re.findall(r"[a-zA-Z][a-zA-Z+\-]{3,}", str(snippet).lower())[:12])
    stop = {
        "with", "from", "that", "this", "have", "been", "were", "their", "into",
        "your", "about", "other", "such", "than", "also", "will", "role", "work",
        "team", "years", "year", "experience", "required", "minimum", "using",
    }
    return {t for t in terms if t not in stop and len(t) > 3}


def _score_text(text: str, terms: set[str]) -> int:
    haystack = text.lower()
    return sum(1 for term in terms if term and term in haystack)


def relevant_bullets_for_experience(
    experience: dict,
    terms: set[str],
    *,
    max_bullets: int,
) -> list[dict]:
    """Pick job-relevant achievements/responsibilities for one role. Never invent text."""
    candidates: list[tuple[int, int, str, list[str]]] = []
    order = 0
    exp_id = experience.get("id") or ""
    for achievement in experience.get("achievements") or []:
        if isinstance(achievement, dict):
            text = (achievement.get("description") or achievement.get("title") or "").strip()
            metric = (achievement.get("quantified_result") or "").strip()
            if metric and metric not in text:
                text = f"{text} ({metric})" if text else metric
            eids = [eid for eid in [achievement.get("id"), exp_id] if eid]
        else:
            text = str(achievement).strip()
            eids = [exp_id] if exp_id else []
        if text:
            candidates.append((_score_text(text, terms), order, text, eids))
            order += 1
    for resp in experience.get("responsibilities") or []:
        text = str(resp).strip()
        if text:
            candidates.append((_score_text(text, terms), order, text, [exp_id] if exp_id else []))
            order += 1
    if not candidates:
        description = (experience.get("description") or "").strip()
        if description:
            candidates.append((_score_text(description, terms), 0, description, [exp_id] if exp_id else []))
    # Direct keyword matches first, then fill remaining slots with next-best
    # related activities so a role is not undersold by a single hit.
    candidates.sort(key=lambda item: (-item[0], item[1]))
    selected = candidates[: max(1, max_bullets)] if candidates else []
    return [{"text": text, "evidence_ids": eids} for _, _, text, eids in selected]


def _entry_from_experience(experience: dict, terms: set[str], max_bullets: int) -> dict:
    return {
        "experience_id": experience.get("id") or "",
        "organization": experience.get("organization") or "",
        "job_title": experience.get("job_title") or "",
        "start_date": experience.get("start_date") or "",
        "end_date": experience.get("end_date") or "Present",
        "location": experience.get("location") or "",
        "bullets": relevant_bullets_for_experience(experience, terms, max_bullets=max_bullets),
    }


def ensure_all_experiences(
    content: dict,
    experiences: list[dict],
    *,
    strategy: dict | None = None,
    job: dict | None = None,
    matches: list[dict] | None = None,
) -> dict:
    """Guarantee every knowledge-base role appears; tailor missing roles to the job."""
    if not experiences:
        return content
    strategy = strategy or {}
    terms = relevance_terms(job, strategy, matches)
    priority = set(strategy.get("priority_experience") or [])
    de_emphasis = set(strategy.get("de_emphasis") or [])

    generated = list(content.get("experience") or [])
    used: set[int] = set()

    def take_generated(experience: dict) -> dict | None:
        exp_id = str(experience.get("id") or "")
        for idx, entry in enumerate(generated):
            if idx in used:
                continue
            entry_id = str(entry.get("experience_id") or "")
            if exp_id and entry_id and entry_id == exp_id:
                used.add(idx)
                entry["experience_id"] = exp_id
                return entry
            if _same_role(
                experience.get("organization"),
                experience.get("job_title"),
                entry.get("organization"),
                entry.get("job_title"),
            ):
                used.add(idx)
                if exp_id:
                    entry["experience_id"] = exp_id
                return entry
        return None

    merged: list[dict] = []
    for experience in experiences:
        exp_id = str(experience.get("id") or "")
        if exp_id in de_emphasis:
            limit = 2
        elif exp_id in priority:
            limit = 6
        else:
            limit = 4
        existing = take_generated(experience)
        if existing:
            if not existing.get("bullets"):
                existing["bullets"] = relevant_bullets_for_experience(experience, terms, max_bullets=limit)
            merged.append(existing)
        else:
            merged.append(_entry_from_experience(experience, terms, limit))

    leftovers = []
    for idx, entry in enumerate(generated):
        if idx in used:
            continue
        duplicate = any(
            _same_role(
                entry.get("organization"),
                entry.get("job_title"),
                item.get("organization"),
                item.get("job_title"),
            )
            for item in merged
        )
        if not duplicate:
            leftovers.append(entry)
    merged.extend(leftovers)
    merged.sort(key=_date_sort_key, reverse=True)
    content["experience"] = merged
    return content


def sanitize_cv_content(content: dict) -> dict:
    summary, summary_ids = sanitize_prose_field(content.get("summary"), content.get("summary_evidence_ids"))
    content["summary"] = summary
    content["summary_evidence_ids"] = summary_ids
    for entry in content.get("experience") or []:
        for bullet in entry.get("bullets") or []:
            if not isinstance(bullet, dict):
                continue
            text, ids = sanitize_prose_field(bullet.get("text"), bullet.get("evidence_ids"))
            bullet["text"] = text
            bullet["evidence_ids"] = ids
    return content


def sanitize_cover_letter_content(content: dict) -> dict:
    paragraphs = []
    for para in content.get("paragraphs") or []:
        if isinstance(para, str):
            text, ids = sanitize_prose_field(para, [])
            paragraphs.append({"text": text, "evidence_ids": ids})
            continue
        text, ids = sanitize_prose_field(para.get("text"), para.get("evidence_ids"))
        para = dict(para)
        para["text"] = text
        para["evidence_ids"] = ids
        paragraphs.append(para)
    content["paragraphs"] = paragraphs
    return content
