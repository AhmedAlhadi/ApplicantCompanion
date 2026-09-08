"""Content-language policy for LLM prompts and generated prose."""
from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

Language = Literal["ar", "en"]
SUPPORTED_LANGUAGES = ("ar", "en")
DEFAULT_LANGUAGE = "ar"

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


def normalize_language(value: Any, default: str = DEFAULT_LANGUAGE) -> str:
    if isinstance(value, str) and value.lower() in SUPPORTED_LANGUAGES:
        return value.lower()
    return default


def output_language_block(language: str) -> str:
    return OUTPUT_LANGUAGE_POLICY[normalize_language(language)]


def content_language_for_user(db: Session, user_id: str) -> str:
    from ..services.settings import get_user_setting

    return normalize_language(get_user_setting(db, user_id, "content_language", DEFAULT_LANGUAGE))


def ui_language_for_user(db: Session, user_id: str) -> str:
    from ..services.settings import get_user_setting

    return normalize_language(get_user_setting(db, user_id, "ui_language", DEFAULT_LANGUAGE))
