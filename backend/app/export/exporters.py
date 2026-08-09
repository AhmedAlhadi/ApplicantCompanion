"""PDF / DOCX export (§50). Preserves layout, typography, section hierarchy."""
from __future__ import annotations

import io


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return (0.0, 0.0, 0.0)
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def export_pdf(document_type: str, content: dict, profile: dict, template_config: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

    typo = template_config.get("typography", {})
    spacing = template_config.get("spacing", {})
    colors = template_config.get("colors", {})
    layout = template_config.get("layout", {})

    buffer = io.BytesIO()
    margin = spacing.get("margins", 54)
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
        title=profile.get("full_name", "Document"),
    )

    body_font = typo.get("body_font", "Helvetica")
    heading_font = typo.get("heading_font", "Helvetica-Bold")
    body_size = typo.get("body_size", 10)
    heading_size = typo.get("heading_size", 13)
    name_size = typo.get("name_size", 20)
    accent = _hex_to_rgb(colors.get("accent", "#2d6cdf"))
    heading_color = _hex_to_rgb(colors.get("heading", "#1a1a2e"))
    body_color = _hex_to_rgb(colors.get("body", "#222222"))
    muted = _hex_to_rgb(colors.get("muted", "#666666"))
    section_gap = spacing.get("section_gap", 14)
    entry_gap = spacing.get("entry_gap", 8)

    name_style = ParagraphStyle("name", fontName=heading_font, fontSize=name_size, textColor=heading_color, spaceAfter=2)
    headline_style = ParagraphStyle("headline", fontName=body_font, fontSize=body_size + 1, textColor=muted, spaceAfter=2)
    h_style = ParagraphStyle("h", fontName=heading_font, fontSize=heading_size, textColor=accent, spaceBefore=section_gap, spaceAfter=4)
    b_style = ParagraphStyle("b", fontName=body_font, fontSize=body_size, textColor=body_color, leading=body_size * 1.35)
    bullet_style = ParagraphStyle("bullet", parent=b_style, leftIndent=spacing.get("bullet_indent", 12), bulletIndent=0, spaceAfter=2)
    entry_style = ParagraphStyle("entry", fontName=heading_font, fontSize=body_size + 1, textColor=heading_color, spaceBefore=entry_gap)
    date_style = ParagraphStyle("date", fontName=body_font, fontSize=body_size - 1, textColor=muted, spaceAfter=2)

    story: list = []
    bullet_char = layout.get("bullet_char", "•")

    def rule():
        if layout.get("header_rule"):
            story.append(HRFlowable(width="100%", thickness=0.7, color=accent, spaceBefore=2, spaceAfter=6))

    if document_type == "cv":
        if profile.get("full_name"):
            story.append(Paragraph(profile["full_name"], name_style))
        if content.get("headline"):
            story.append(Paragraph(content["headline"], headline_style))
        contact = " | ".join(p for p in [profile.get("email", ""), profile.get("phone", ""), profile.get("location", "")] if p)
        if contact:
            story.append(Paragraph(contact, date_style))
        rule()

        if content.get("summary"):
            story.append(Paragraph("PROFESSIONAL SUMMARY", h_style))
            story.append(Paragraph(content["summary"], b_style))

        if content.get("experience"):
            story.append(Paragraph("PROFESSIONAL EXPERIENCE", h_style))
            for entry in content["experience"]:
                header = f"{entry.get('job_title', '')}, {entry.get('organization', '')}"
                story.append(Paragraph(header, entry_style))
                dates = " – ".join(p for p in [entry.get("start_date", ""), entry.get("end_date", "")] if p)
                loc = entry.get("location", "")
                meta = " | ".join(p for p in [dates, loc] if p)
                if meta:
                    story.append(Paragraph(meta, date_style))
                for bullet in entry.get("bullets", []):
                    text = bullet.get("text", bullet) if isinstance(bullet, dict) else str(bullet)
                    story.append(Paragraph(text, bullet_style, bulletText=bullet_char))

        if content.get("skills"):
            story.append(Paragraph("SKILLS", h_style))
            story.append(Paragraph(", ".join(content["skills"]), b_style))

        if content.get("education"):
            story.append(Paragraph("EDUCATION", h_style))
            for ed in content["education"]:
                parts = [ed.get("degree", ""), ed.get("field_of_study", ""), ed.get("institution", "")]
                story.append(Paragraph(", ".join(p for p in parts if p), entry_style))
                dates = " – ".join(p for p in [ed.get("start_date", ""), ed.get("end_date", "")] if p)
                if dates:
                    story.append(Paragraph(dates, date_style))

        if content.get("certifications"):
            story.append(Paragraph("CERTIFICATIONS", h_style))
            for cert in content["certifications"]:
                story.append(Paragraph(cert, bullet_style, bulletText=bullet_char))

        if content.get("languages"):
            story.append(Paragraph("LANGUAGES", h_style))
            story.append(Paragraph(
                ", ".join(f"{l.get('language', '')} ({l.get('proficiency', '')})".strip(" ()") for l in content["languages"]),
                b_style,
            ))

        for section in content.get("additional_sections", []):
            story.append(Paragraph(section.get("name", "ADDITIONAL").upper(), h_style))
            for entry in section.get("entries", []):
                text = entry.get("text", entry) if isinstance(entry, dict) else str(entry)
                story.append(Paragraph(text, bullet_style, bulletText=bullet_char))
    else:
        if profile.get("full_name"):
            story.append(Paragraph(profile["full_name"], name_style))
        contact = " | ".join(p for p in [profile.get("email", ""), profile.get("phone", ""), profile.get("location", "")] if p)
        if contact:
            story.append(Paragraph(contact, date_style))
        story.append(Spacer(1, 8 * mm))
        if content.get("subject"):
            story.append(Paragraph(f"<b>{content['subject']}</b>", b_style))
            story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(content.get("salutation", "Dear Hiring Manager,"), b_style))
        story.append(Spacer(1, 3 * mm))
        for para in content.get("paragraphs", []):
            text = para.get("text", "") if isinstance(para, dict) else str(para)
            if text:
                story.append(Paragraph(text, b_style))
                story.append(Spacer(1, 3 * mm))
        story.append(Spacer(1, 4 * mm))
        for line in content.get("closing", "Sincerely,").split("\n"):
            story.append(Paragraph(line, b_style))

    doc.build(story)
    return buffer.getvalue()


def export_docx(document_type: str, content: dict, profile: dict, template_config: dict) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor

    typo = template_config.get("typography", {})
    colors = template_config.get("colors", {})
    layout = template_config.get("layout", {})

    document = Document()
    style = document.styles["Normal"]
    style.font.name = typo.get("body_font", "Helvetica").replace("-Roman", "").replace("-Bold", "")
    style.font.size = Pt(typo.get("body_size", 10))

    accent = _hex_to_rgb(colors.get("accent", "#2d6cdf"))
    accent_rgb = RGBColor(*(int(c * 255) for c in accent))
    bullet_char = layout.get("bullet_char", "•")

    def heading(text: str):
        p = document.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(typo.get("heading_size", 13))
        run.font.color.rgb = accent_rgb
        return p

    def bullet(text: str):
        return document.add_paragraph(f"{bullet_char} {text}" if bullet_char else text)

    if document_type == "cv":
        name = document.add_paragraph()
        run = name.add_run(profile.get("full_name", ""))
        run.bold = True
        run.font.size = Pt(typo.get("name_size", 20))
        if content.get("headline"):
            document.add_paragraph(content["headline"])
        contact = " | ".join(p for p in [profile.get("email", ""), profile.get("phone", ""), profile.get("location", "")] if p)
        if contact:
            document.add_paragraph(contact)

        if content.get("summary"):
            heading("PROFESSIONAL SUMMARY")
            document.add_paragraph(content["summary"])
        if content.get("experience"):
            heading("PROFESSIONAL EXPERIENCE")
            for entry in content["experience"]:
                p = document.add_paragraph()
                r = p.add_run(f"{entry.get('job_title', '')}, {entry.get('organization', '')}")
                r.bold = True
                dates = " – ".join(x for x in [entry.get("start_date", ""), entry.get("end_date", "")] if x)
                meta = " | ".join(x for x in [dates, entry.get("location", "")] if x)
                if meta:
                    document.add_paragraph(meta)
                for b in entry.get("bullets", []):
                    bullet(b.get("text", b) if isinstance(b, dict) else str(b))
        if content.get("skills"):
            heading("SKILLS")
            document.add_paragraph(", ".join(content["skills"]))
        if content.get("education"):
            heading("EDUCATION")
            for ed in content["education"]:
                parts = [ed.get("degree", ""), ed.get("field_of_study", ""), ed.get("institution", "")]
                document.add_paragraph(", ".join(p for p in parts if p))
        if content.get("certifications"):
            heading("CERTIFICATIONS")
            for cert in content["certifications"]:
                bullet(cert)
        if content.get("languages"):
            heading("LANGUAGES")
            document.add_paragraph(
                ", ".join(f"{l.get('language', '')} ({l.get('proficiency', '')})".strip(" ()") for l in content["languages"])
            )
        for section in content.get("additional_sections", []):
            heading(section.get("name", "ADDITIONAL").upper())
            for entry in section.get("entries", []):
                bullet(entry.get("text", entry) if isinstance(entry, dict) else str(entry))
    else:
        if profile.get("full_name"):
            p = document.add_paragraph()
            r = p.add_run(profile["full_name"])
            r.bold = True
            r.font.size = Pt(typo.get("name_size", 16))
        contact = " | ".join(p for p in [profile.get("email", ""), profile.get("phone", ""), profile.get("location", "")] if p)
        if contact:
            document.add_paragraph(contact)
        document.add_paragraph("")
        if content.get("subject"):
            p = document.add_paragraph()
            p.add_run(content["subject"]).bold = True
        document.add_paragraph(content.get("salutation", "Dear Hiring Manager,"))
        for para in content.get("paragraphs", []):
            text = para.get("text", "") if isinstance(para, dict) else str(para)
            if text:
                document.add_paragraph(text)
        for line in content.get("closing", "Sincerely,").split("\n"):
            document.add_paragraph(line)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def export_document(fmt: str, document_type: str, content: dict, profile: dict, template_config: dict) -> tuple[bytes, str]:
    if fmt == "pdf":
        return export_pdf(document_type, content, profile, template_config), "application/pdf"
    if fmt == "docx":
        return export_docx(document_type, content, profile, template_config), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    raise ValueError(f"Unsupported export format: {fmt}")
