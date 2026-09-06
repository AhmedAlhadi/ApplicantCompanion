"""Strip leaked evidence identifiers from generated document prose.

Agents must cite knowledge-base ids in structured `evidence_ids` fields so the
UI can show [View Evidence]. Models sometimes paste those ids into the visible
text (e.g. "(Evidence: <uuid>, <uuid>)"). This module removes that leakage and
recovers the ids so they can be merged back into the structured field.
"""
from __future__ import annotations

import re

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
UUID_RE = re.compile(UUID)

_EVIDENCE_BLOCK_RE = re.compile(
    rf"""
    \s*
    [\(\[]
    \s*
    (?:evidence(?:\s*ids?)?|source(?:s)?|refs?|citations?)
    \s*:?\s*
    (?P<ids>(?:{UUID})(?:\s*,\s*{UUID})*)
    \s*
    [\)\]]
    \.?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_EVIDENCE_LABEL_RE = re.compile(
    rf"""
    (?:[,;.]?\s*)
    (?:evidence(?:\s*ids?)?)\s*:\s*
    (?P<ids>(?:{UUID})(?:\s*,\s*{UUID})*)
    \.?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_UUID_PAREN_RE = re.compile(
    rf"""
    \s*
    [\(\[]
    \s*
    (?P<ids>(?:{UUID})(?:\s*,\s*{UUID})*)
    \s*
    [\)\]]
    \.?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _ids_from(match: re.Match[str]) -> list[str]:
    return UUID_RE.findall(match.group("ids") or "")


def strip_inline_evidence(text: str | None) -> tuple[str, list[str]]:
    """Return (cleaned prose, evidence ids that were embedded in the text)."""
    if not text:
        return "", []
    extracted: list[str] = []

    def _take(match: re.Match[str]) -> str:
        extracted.extend(_ids_from(match))
        return ""

    cleaned = _EVIDENCE_BLOCK_RE.sub(_take, text)
    cleaned = _EVIDENCE_LABEL_RE.sub(_take, cleaned)
    cleaned = _UUID_PAREN_RE.sub(_take, cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s+\n", "\n", cleaned)
    return cleaned.strip(), list(dict.fromkeys(extracted))


def merge_evidence_ids(*groups: list[str] | None) -> list[str]:
    out: list[str] = []
    for group in groups:
        for item in group or []:
            if item and item not in out:
                out.append(item)
    return out


def sanitize_prose_field(text: str | None, existing_ids: list[str] | None = None) -> tuple[str, list[str]]:
    cleaned, extracted = strip_inline_evidence(text)
    return cleaned, merge_evidence_ids(existing_ids, extracted)


def cited_ids_from_content(content: dict | None, doc_type: str) -> list[str]:
    """Collect structured evidence ids plus any UUIDs leaked into visible prose."""
    content = content or {}
    cited: list[str] = []
    if doc_type == "cv":
        _, summary_ids = sanitize_prose_field(content.get("summary"), content.get("summary_evidence_ids"))
        cited.extend(summary_ids)
        for entry in content.get("experience") or []:
            for bullet in entry.get("bullets") or []:
                if isinstance(bullet, dict):
                    _, ids = sanitize_prose_field(bullet.get("text"), bullet.get("evidence_ids"))
                else:
                    _, ids = strip_inline_evidence(str(bullet))
                cited.extend(ids)
    else:
        for para in content.get("paragraphs") or []:
            if isinstance(para, str):
                _, ids = strip_inline_evidence(para)
            else:
                _, ids = sanitize_prose_field(para.get("text"), para.get("evidence_ids"))
            cited.extend(ids)
    return merge_evidence_ids(cited)
