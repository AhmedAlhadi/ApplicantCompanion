"""Language settings, Arabic parsing heuristics, and prompt policy."""
from __future__ import annotations

import io

from app.llm import mock_logic
from app.prompts.language import DEFAULT_LANGUAGE, output_language_block
from app.qualification import degree_level
from app.services.deadlines import extract_application_deadline, normalize_application_deadline


_AR_JD = """
المسمى الوظيفي: محلل بيانات
الجهة: اليونيسف
الموقع: عمّان، الأردن
آخر موعد للتقديم: 15 سبتمبر 2026
نوع العقد: محدد المدة

المسؤوليات:
- بناء لوحات معلومات Power BI

المتطلبات:
- خبرة في Python
- بكالوريوس في علوم الحاسوب
"""

_AR_CV = """
أحمد علي
عمّان، الأردن

الخبرة العملية
محلل بيانات، اليونيسف
يناير 2020 – حتى الآن
- تطوير لوحات Power BI

التعليم
بكالوريوس علوم الحاسوب، الجامعة الأردنية

المهارات
Python
Power BI
SQL

اللغات
العربية (لغة أم)
الإنجليزية (طلق)
"""


def test_settings_default_languages_are_arabic(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ui_language"] == DEFAULT_LANGUAGE == "ar"
    assert data["content_language"] == "ar"


def test_settings_language_round_trip(client, auth_headers):
    try:
        resp = client.put("/api/settings", headers=auth_headers, json={
            "ui_language": "en",
            "content_language": "en",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ui_language"] == "en"
        assert data["content_language"] == "en"
        again = client.get("/api/settings", headers=auth_headers)
        assert again.json()["ui_language"] == "en"
        assert again.json()["content_language"] == "en"
    finally:
        client.put("/api/settings", headers=auth_headers, json={
            "ui_language": "ar",
            "content_language": "ar",
        })


def test_settings_rejects_unknown_language(client, auth_headers):
    resp = client.put("/api/settings", headers=auth_headers, json={"ui_language": "fr"})
    assert resp.status_code == 422


def test_arabic_deadline_labels_and_months():
    assert normalize_application_deadline("15 سبتمبر 2026") == "2026-09-15"
    assert normalize_application_deadline("15 أيلول 2026") == "2026-09-15"
    assert extract_application_deadline("آخر موعد للتقديم: 15 سبتمبر 2026") == "2026-09-15"
    assert extract_application_deadline("تاريخ الإغلاق: 2026-09-01") == "2026-09-01"


def test_arabic_degree_synonyms():
    assert degree_level("بكالوريوس") == degree_level("bachelor")
    assert degree_level("ماجستير") == degree_level("master")
    assert degree_level("دكتوراه") == degree_level("phd")
    assert degree_level("ثانوية عامة") == degree_level("secondary")
    assert degree_level("توجيهي") == 1


def test_arabic_tokens_are_kept():
    toks = mock_logic.tokens("خبرة في تحليل البيانات باستخدام Python")
    assert "خبرة" in toks
    assert "python" in toks


def test_mock_parses_arabic_job_ad():
    result = mock_logic.mock_jd_analysis(f"<job_description>{_AR_JD}</job_description>")
    pos = result["position"]
    assert pos["job_title"] == "محلل بيانات"
    assert pos["organization"] == "اليونيسف"
    assert pos["deadline"] == "2026-09-15"
    texts = " ".join(r["text"] for r in result["requirements"])
    assert "Python" in texts or "python" in texts.lower()


def test_mock_extracts_arabic_cv_sections():
    result = mock_logic.mock_career_extraction(f"<document_text>{_AR_CV}</document_text>")
    assert result["experiences"], result
    assert any("يونيسف" in (e.get("organization") or "") or "بيانات" in (e.get("job_title") or "") for e in result["experiences"])
    skill_names = " ".join(s.get("name", "") if isinstance(s, dict) else str(s) for s in result.get("skills", []))
    assert "Python" in skill_names or "python" in skill_names.lower() or "Power" in skill_names


def test_arabic_output_language_shapes_scoring_narrative():
    payload = '{"matches": [], "overall_score": 0.5}'
    english = mock_logic.mock_scoring(payload)
    arabic = mock_logic.mock_scoring("OUTPUT_LANGUAGE: ar\n" + payload)
    assert "Overall fit" in english["explanation"]
    assert "الملاءمة" in arabic["explanation"]


def test_output_language_block_mentions_arabic():
    block = output_language_block("ar")
    assert "OUTPUT_LANGUAGE: ar" in block
    assert "Modern Standard Arabic" in block


def test_base_agent_injects_arabic_output_language(db, monkeypatch):
    from app.agents.base import AgentContext, BaseAgent
    from app.llm.base import LLMResponse
    from app.llm.router import RoutedModel

    class _LangAgent(BaseAgent):
        name = "lang_harness"
        prompt_name = "scoring"
        output_model = None

        def build_user_message(self, **kwargs) -> str:
            return "payload"

    captured = []

    class _CaptureProvider:
        name = "capture"

        def generate(self, model, request):
            captured.append(request)
            return LLMResponse(text="{}", data={})

    monkeypatch.setattr(
        "app.agents.base.route_task",
        lambda _: RoutedModel(_CaptureProvider(), "test", "test"),
    )
    _LangAgent().run(AgentContext(db=db, user_id="user"))
    assert captured
    assert "OUTPUT LANGUAGE" in captured[0].system
    assert "OUTPUT_LANGUAGE: ar" in captured[0].system
    assert captured[0].user.startswith("OUTPUT_LANGUAGE: ar")


def test_arabic_export_headings_in_docx():
    import zipfile

    from app.export.exporters import export_docx

    data = export_docx(
        "cv",
        {
            "headline": "محلل بيانات",
            "summary": "ملخص مهني",
            "skills": ["Python"],
            "experience": [],
        },
        {"full_name": "أحمد علي"},
        {},
        content_language="ar",
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "المهارات" in xml
    assert "الملخص المهني" in xml
    from app.export.exporters import export_pdf

    pdf = export_pdf(
        "cv",
        {"headline": "محلل بيانات", "summary": "ملخص مهني", "skills": ["Python"]},
        {"full_name": "أحمد علي"},
        {},
        content_language="ar",
    )
    assert pdf.startswith(b"%PDF")


def test_pypdf_extracts_arabic_text():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    from app.export.exporters import _FONTS_DIR
    from app.services.ingestion import extract_text

    font_path = _FONTS_DIR / "IBMPlexSansArabic-Regular.ttf"
    assert font_path.is_file()
    pdfmetrics.registerFont(TTFont("PlexArTest", str(font_path)))
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont("PlexArTest", 14)
    c.drawString(72, 720, "محلل بيانات")
    c.save()
    text = extract_text("cv.pdf", buf.getvalue())
    expected = set("محللبيانات")
    assert expected <= set(text), text
    assert any("\u0600" <= ch <= "\u06FF" for ch in text)
