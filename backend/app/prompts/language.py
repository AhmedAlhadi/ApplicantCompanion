"""Content-language policy for LLM prompts and generated prose."""
from __future__ import annotations

import re
from typing import Any, Literal

from sqlalchemy.orm import Session

Language = Literal["ar", "en"]
SUPPORTED_LANGUAGES = ("ar", "en")
DEFAULT_LANGUAGE = "ar"

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")

OUTPUT_LANGUAGE_POLICY = {
    "ar": (
        "OUTPUT LANGUAGE\n"
        "Write all free-text fields (summary, explanation, risks, advantages, notes, "
        "strategy prose, CV and cover-letter body, qualification path labels that are "
        "not schema enums) in Modern Standard Arabic.\n"
        "Keep JSON keys and schema enum values in English exactly as specified "
        "(MATCHED, PARTIALLY_MATCHED, TRANSFERABLE, NOT_MATCHED, UNKNOWN, CRITICAL, "
        "HIGH, MEDIUM, LOW, technical_skill, bachelor, master, phd, secondary, etc.).\n"
        "Preserve original source wording for quoted requirement text, experience "
        "bullets, and other verbatim extracts.\n"
        "OUTPUT_LANGUAGE: ar"
    ),
    "en": (
        "OUTPUT LANGUAGE\n"
        "Write all free-text fields (summary, explanation, risks, advantages, notes, "
        "strategy prose, CV and cover-letter body) in English.\n"
        "Keep JSON keys and schema enum values in English exactly as specified.\n"
        "Preserve original source wording for quoted requirement text, experience "
        "bullets, and other verbatim extracts.\n"
        "OUTPUT_LANGUAGE: en"
    ),
}

CONVERSATIONAL_OUTPUT_LANGUAGE_POLICY = {
    "ar": (
        "OUTPUT LANGUAGE\n"
        "The user's question is in Arabic. Write the `answer` field in Modern Standard Arabic.\n"
        "Do not switch to English because this prompt, JSON schema, or evidence snippets "
        "are in English.\n"
        "Keep JSON keys, schema enum values, and citation ids in English exactly as specified.\n"
        "Quoted evidence may remain in its original language.\n"
        "OUTPUT_LANGUAGE: ar"
    ),
    "en": (
        "OUTPUT LANGUAGE\n"
        "The user's question is in English. Write the `answer` field in English.\n"
        "Keep JSON keys, schema enum values, and citation ids in English exactly as specified.\n"
        "Quoted evidence may remain in its original language.\n"
        "OUTPUT_LANGUAGE: en"
    ),
}


def normalize_language(value: Any, default: str = DEFAULT_LANGUAGE) -> str:
    if isinstance(value, str) and value.lower() in SUPPORTED_LANGUAGES:
        return value.lower()
    return default


def output_language_block(language: str) -> str:
    return OUTPUT_LANGUAGE_POLICY[normalize_language(language)]


def conversational_output_language_block(language: str) -> str:
    return CONVERSATIONAL_OUTPUT_LANGUAGE_POLICY[normalize_language(language)]


def content_language_for_user(db: Session, user_id: str) -> str:
    from ..services.settings import get_user_setting

    return normalize_language(get_user_setting(db, user_id, "content_language", DEFAULT_LANGUAGE))


def ui_language_for_user(db: Session, user_id: str) -> str:
    from ..services.settings import get_user_setting

    return normalize_language(get_user_setting(db, user_id, "ui_language", DEFAULT_LANGUAGE))


def detect_text_language(text: str) -> str | None:
    """Return ar/en when the sample has a clear script; None if too short or mixed-empty."""
    sample = (text or "").strip()
    if not sample:
        return None
    arabic = len(_ARABIC_RE.findall(sample))
    if arabic >= 2:
        return "ar"
    latin = len(_LATIN_RE.findall(sample))
    if latin >= 2:
        return "en"
    return None


def reply_language_for_question(
    question: str,
    history: list | None = None,
    fallback: str = DEFAULT_LANGUAGE,
) -> str:
    """Conversational reply language: current question, then last user turn, then fallback.

    Document `content_language` is intentionally not used — that setting is for
    generated CVs/letters, not chat replies.
    """
    detected = detect_text_language(question)
    if detected:
        return detected
    for turn in reversed(history or []):
        if not isinstance(turn, dict):
            continue
        if str(turn.get("role") or "") != "user":
            continue
        detected = detect_text_language(str(turn.get("content") or ""))
        if detected:
            return detected
    return normalize_language(fallback)
