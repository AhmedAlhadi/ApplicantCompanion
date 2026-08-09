"""Data-driven CV / cover-letter template engine (§28).

A template is pure data — metadata, typography, spacing, sections, colors,
layout, rendering rules — so new themes are configuration, not code. The seven
built-in professional themes each have a matching cover-letter variant.
"""
from __future__ import annotations

from copy import deepcopy

SECTION_ORDER = ["summary", "experience", "skills", "education", "certifications", "languages", "additional"]

_BASE_CV = {
    "metadata": {"document_type": "cv", "version": 1},
    "typography": {"heading_font": "Helvetica-Bold", "body_font": "Helvetica", "heading_size": 13, "body_size": 10, "name_size": 20},
    "spacing": {"section_gap": 14, "entry_gap": 8, "bullet_indent": 12, "margins": 54},
    "sections": SECTION_ORDER,
    "colors": {"heading": "#1a1a2e", "accent": "#2d6cdf", "body": "#222222", "muted": "#666666"},
    "layout": {"columns": 1, "header_rule": True, "bullet_char": "•"},
    "rendering_rules": {
        "ats_friendly": True,
        "standard_headings": True,
        "max_bullets_per_entry": 8,
        "date_format": "MMM YYYY",
    },
}

_BASE_LETTER = {
    "metadata": {"document_type": "cover_letter", "version": 1},
    "typography": {"heading_font": "Helvetica", "body_font": "Helvetica", "heading_size": 12, "body_size": 11, "name_size": 16},
    "spacing": {"section_gap": 12, "entry_gap": 8, "bullet_indent": 0, "margins": 64},
    "sections": ["subject", "salutation", "body", "closing"],
    "colors": {"heading": "#1a1a2e", "accent": "#2d6cdf", "body": "#222222", "muted": "#666666"},
    "layout": {"columns": 1, "header_rule": False, "bullet_char": ""},
    "rendering_rules": {"ats_friendly": True, "standard_headings": True, "max_paragraphs": 6},
}


def _theme(overrides: dict, letter_overrides: dict | None = None) -> tuple[dict, dict]:
    cv = deepcopy(_BASE_CV)
    letter = deepcopy(_BASE_LETTER)
    for key, value in overrides.items():
        if isinstance(value, dict):
            cv[key].update(value)
        else:
            cv[key] = value
    for key, value in (letter_overrides or overrides).items():
        if isinstance(value, dict):
            letter[key].update(value)
        else:
            letter[key] = value
    return cv, letter


BUILTIN_THEMES: dict[str, dict] = {}

_DEFINITIONS = {
    "traditional-executive": (
        "Traditional Executive",
        "Serif headings, conservative palette, classic single-column layout.",
        {
            "typography": {"heading_font": "Times-Bold", "body_font": "Times-Roman", "name_size": 22},
            "colors": {"heading": "#000000", "accent": "#1f3864", "body": "#111111", "muted": "#555555"},
        },
    ),
    "modern-professional": (
        "Modern Professional",
        "Clean sans-serif with a colored accent and generous whitespace.",
        {
            "colors": {"heading": "#0f2540", "accent": "#2d6cdf", "body": "#1f2937", "muted": "#6b7280"},
            "spacing": {"section_gap": 16},
        },
    ),
    "international-un": (
        "International Organization / UN",
        "Formal structure suited to UN and international NGO applications.",
        {
            "typography": {"heading_font": "Helvetica-Bold", "body_font": "Helvetica"},
            "colors": {"heading": "#1a1a1a", "accent": "#0072bc", "body": "#1a1a1a", "muted": "#595959"},
        },
    ),
    "consulting": (
        "Consulting",
        "Dense, achievement-first layout in the style of top consulting CVs.",
        {
            "typography": {"body_size": 9.5},
            "spacing": {"section_gap": 10, "entry_gap": 6},
            "colors": {"heading": "#12284b", "accent": "#12284b", "body": "#1a1a1a", "muted": "#4d4d4d"},
        },
    ),
    "technology-ai": (
        "Technology / AI",
        "Technical-skills-forward theme for engineering and AI roles.",
        {
            "sections": ["summary", "skills", "experience", "education", "certifications", "languages", "additional"],
            "colors": {"heading": "#0b1220", "accent": "#0e7490", "body": "#111827", "muted": "#6b7280"},
        },
        {"sections": ["subject", "salutation", "body", "closing"]},
    ),
    "minimal-ats": (
        "Minimal ATS",
        "Maximum parseability: standard headings, no tables, no graphics.",
        {
            "typography": {"heading_font": "Helvetica-Bold", "body_font": "Helvetica", "heading_size": 12, "name_size": 16},
            "colors": {"heading": "#000000", "accent": "#000000", "body": "#000000", "muted": "#333333"},
            "layout": {"header_rule": False},
        },
    ),
    "academic-research": (
        "Academic / Research",
        "Publication-friendly ordering with education before experience.",
        {
            "sections": ["summary", "education", "experience", "additional", "skills", "certifications", "languages"],
            "typography": {"heading_font": "Times-Bold", "body_font": "Times-Roman"},
            "colors": {"heading": "#1a202c", "accent": "#2b6cb0", "body": "#1a202c", "muted": "#4a5568"},
        },
    ),
}


def build_builtin_templates() -> list[dict]:
    """Return template rows (cv + cover_letter) for every built-in theme."""
    rows = []
    for key, definition in _DEFINITIONS.items():
        name, description, overrides = definition[0], definition[1], definition[2]
        letter_overrides = definition[3] if len(definition) > 3 else None
        cv_config, letter_config = _theme(overrides, letter_overrides)
        rows.append({
            "key": key,
            "name": name,
            "document_type": "cv",
            "description": description,
            "config": cv_config,
            "is_builtin": True,
        })
        rows.append({
            "key": key,
            "name": f"{name} — Cover Letter",
            "document_type": "cover_letter",
            "description": f"Matching cover-letter layout for {name}.",
            "config": letter_config,
            "is_builtin": True,
        })
    return rows
