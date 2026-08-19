"""Render structured document content to plain text (used for ATS analysis,
previews, and as the basis for PDF/DOCX export)."""
from __future__ import annotations

from ..evidence_citations import strip_inline_evidence


def _visible_text(text: str | None) -> str:
    return strip_inline_evidence(text or "")[0]


def render_cv_text(content: dict, profile: dict | None = None) -> str:
    profile = profile or {}
    lines: list[str] = []
    name = profile.get("full_name", "")
    if name:
        lines.append(name.upper())
    if content.get("headline"):
        lines.append(content["headline"])
    contact = " | ".join(
        p for p in [profile.get("email", ""), profile.get("phone", ""), profile.get("location", "")] if p
    )
    if contact:
        lines.append(contact)
    lines.append("")

    if content.get("summary"):
        lines += ["PROFESSIONAL SUMMARY", _visible_text(content["summary"]), ""]

    if content.get("experience"):
        lines.append("PROFESSIONAL EXPERIENCE")
        for entry in content["experience"]:
            dates = " – ".join(p for p in [entry.get("start_date", ""), entry.get("end_date", "")] if p)
            header = f"{entry.get('job_title', '')}, {entry.get('organization', '')}"
            if entry.get("location"):
                header += f" — {entry['location']}"
            lines.append(header)
            if dates:
                lines.append(dates)
            for bullet in entry.get("bullets", []):
                text = bullet.get("text", bullet) if isinstance(bullet, dict) else str(bullet)
                visible = _visible_text(str(text))
                if visible:
                    lines.append(f"• {visible}")
            lines.append("")

    if content.get("skills"):
        lines += ["SKILLS", ", ".join(content["skills"]), ""]

    if content.get("education"):
        lines.append("EDUCATION")
        for ed in content["education"]:
            parts = [ed.get("degree", ""), ed.get("field_of_study", ""), ed.get("institution", "")]
            lines.append(", ".join(p for p in parts if p))
            dates = " – ".join(p for p in [ed.get("start_date", ""), ed.get("end_date", "")] if p)
            if dates:
                lines.append(dates)
        lines.append("")

    if content.get("certifications"):
        lines.append("CERTIFICATIONS")
        lines += [f"• {c}" for c in content["certifications"]]
        lines.append("")

    if content.get("languages"):
        lines.append("LANGUAGES")
        lines.append(
            ", ".join(
                f"{l.get('language', '')} ({l.get('proficiency', '')})".strip(" ()")
                for l in content["languages"]
            )
        )
        lines.append("")

    for section in content.get("additional_sections", []):
        lines.append(section.get("name", "ADDITIONAL").upper())
        for entry in section.get("entries", []):
            lines.append(f"• {entry.get('text', entry) if isinstance(entry, dict) else entry}")
        lines.append("")

    return "\n".join(lines).strip()


def render_cover_letter_text(content: dict, profile: dict | None = None) -> str:
    profile = profile or {}
    lines: list[str] = []
    if profile.get("full_name"):
        lines.append(profile["full_name"])
    contact = " | ".join(
        p for p in [profile.get("email", ""), profile.get("phone", ""), profile.get("location", "")] if p
    )
    if contact:
        lines.append(contact)
    lines.append("")
    if content.get("subject"):
        lines += [f"Subject: {content['subject']}", ""]
    lines += [content.get("salutation", "Dear Hiring Manager,"), ""]
    for para in content.get("paragraphs", []):
        text = para.get("text", "") if isinstance(para, dict) else str(para)
        visible = _visible_text(str(text))
        if visible:
            lines += [visible, ""]
    lines.append(content.get("closing", "Sincerely,"))
    return "\n".join(lines).strip()


def render_text(document_type: str, content: dict, profile: dict | None = None) -> str:
    if document_type == "cover_letter":
        return render_cover_letter_text(content, profile)
    return render_cv_text(content, profile)
