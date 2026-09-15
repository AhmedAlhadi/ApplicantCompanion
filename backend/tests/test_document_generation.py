from __future__ import annotations

from app.evidence_citations import cited_ids_from_content, strip_inline_evidence
from app.prompts.registry import load_prompt
from app.schemas.agents import CoverLetterParagraph, GeneratedCoverLetter, GeneratedCV
from app.services.document_postprocess import ensure_all_experiences, sanitize_cover_letter_content
from app.templates.renderer import render_cover_letter_text


def test_latest_cv_prompt_requires_all_experiences():
    prompt = load_prompt("cv_generation")
    assert prompt.version == "v3"
    assert "EVERY experience" in prompt.system
    assert "NEVER write ids" in prompt.system


def test_latest_cover_letter_prompt_forbids_inline_ids():
    prompt = load_prompt("cover_letter_generation")
    assert prompt.version == "v3"
    assert "View Evidence" in prompt.system
    assert "NEVER include" in prompt.system


def test_strips_evidence_parenthetical_from_cover_letter_prose():
    text = (
        "I have contributed to achieving the Sustainable Development Goals. "
        "(Evidence: 387bfed5-433b-4291-b28a-720c01d5ed3c, 567fc646-37d9-4a6a-9f15-9d08cca3dd05)"
    )
    cleaned, ids = strip_inline_evidence(text)
    assert "Evidence" not in cleaned
    assert "387bfed5" not in cleaned
    assert cleaned.endswith("Goals.")
    assert ids == [
        "387bfed5-433b-4291-b28a-720c01d5ed3c",
        "567fc646-37d9-4a6a-9f15-9d08cca3dd05",
    ]


def test_cover_letter_schema_moves_inline_ids_into_evidence_field():
    para = CoverLetterParagraph.model_validate({
        "text": (
            "I led UNICEF's information management work "
            "(Evidence: 387bfed5-433b-4291-b28a-720c01d5ed3c)."
        ),
        "evidence_ids": [],
    })
    assert "Evidence" not in para.text
    assert "387bfed5" not in para.text
    assert para.evidence_ids == ["387bfed5-433b-4291-b28a-720c01d5ed3c"]


def test_cover_letter_render_hides_leaked_ids():
    rendered = render_cover_letter_text({
        "salutation": "Dear Hiring Manager,",
        "paragraphs": [{
            "text": "Fit for the role. (Evidence: 387bfed5-433b-4291-b28a-720c01d5ed3c)",
            "evidence_ids": ["387bfed5-433b-4291-b28a-720c01d5ed3c"],
        }],
        "closing": "Sincerely,",
    })
    assert "Evidence" not in rendered
    assert "387bfed5" not in rendered
    assert "Fit for the role." in rendered


def test_sanitize_cover_letter_merges_extracted_ids():
    content = sanitize_cover_letter_content({
        "paragraphs": [{
            "text": "Delivered the MIS rollout (Evidence: 11111111-1111-1111-1111-111111111111).",
            "evidence_ids": ["22222222-2222-2222-2222-222222222222"],
        }]
    })
    para = content["paragraphs"][0]
    assert "Evidence" not in para["text"]
    assert para["evidence_ids"] == [
        "22222222-2222-2222-2222-222222222222",
        "11111111-1111-1111-1111-111111111111",
    ]


def test_ensure_all_experiences_fills_roles_the_model_omitted():
    experiences = [
        {
            "id": "e1",
            "organization": "UNDP",
            "job_title": "Information Management Officer",
            "start_date": "2022-01",
            "end_date": "",
            "location": "Amman",
            "achievements": [{"id": "a1", "description": "Built Power BI dashboards for programme monitoring"}],
            "responsibilities": ["Lead digital transformation"],
        },
        {
            "id": "e2",
            "organization": "UNICEF",
            "job_title": "Data Analyst",
            "start_date": "2018-01",
            "end_date": "2021-12",
            "location": "Amman",
            "achievements": [{"id": "a2", "description": "Designed a warehouse for education indicators"}],
            "responsibilities": ["Prepared donor reports"],
        },
        {
            "id": "e3",
            "organization": "Local NGO",
            "job_title": "Intern",
            "start_date": "2016-06",
            "end_date": "2016-12",
            "responsibilities": ["Filed paper archives", "Supported logistics for a field survey"],
        },
    ]
    content = {
        "experience": [{
            "experience_id": "e1",
            "organization": "UNDP",
            "job_title": "Information Management Officer",
            "start_date": "2022-01",
            "end_date": "",
            "bullets": [{"text": "Built Power BI dashboards for programme monitoring", "evidence_ids": ["a1"]}],
        }]
    }
    result = ensure_all_experiences(
        content,
        experiences,
        strategy={"priority_experience": ["e1"], "de_emphasis": ["e3"], "keywords": ["Power BI", "data"]},
        job={"position_title": "Information Management Officer", "parsed": {"keywords": [{"term": "Power BI"}]}},
        matches=[],
    )
    orgs = [entry["organization"] for entry in result["experience"]]
    assert orgs == ["UNDP", "UNICEF", "Local NGO"]
    intern = result["experience"][2]
    assert intern["experience_id"] == "e3"
    assert intern["bullets"]
    assert len(intern["bullets"]) <= 2


def test_cited_ids_include_inline_leaked_evidence():
    ids = cited_ids_from_content(
        {
            "summary": "Lead. (Evidence: 387bfed5-433b-4291-b28a-720c01d5ed3c)",
            "summary_evidence_ids": [],
            "experience": [{
                "bullets": [{
                    "text": "Built dashboards (Evidence: 567fc646-37d9-4a6a-9f15-9d08cca3dd05)",
                    "evidence_ids": ["11111111-1111-1111-1111-111111111111"],
                }]
            }],
        },
        "cv",
    )
    assert ids == [
        "387bfed5-433b-4291-b28a-720c01d5ed3c",
        "11111111-1111-1111-1111-111111111111",
        "567fc646-37d9-4a6a-9f15-9d08cca3dd05",
    ]


def test_cited_ids_from_cover_letter_paragraphs():
    ids = cited_ids_from_content(
        {
            "paragraphs": [{
                "text": "I led UNICEF IM work (Evidence: 387bfed5-433b-4291-b28a-720c01d5ed3c).",
                "evidence_ids": [],
            }]
        },
        "cover_letter",
    )
    assert ids == ["387bfed5-433b-4291-b28a-720c01d5ed3c"]


def test_relevant_bullets_fill_related_when_few_direct_matches():
    experiences = [{
        "id": "e1",
        "organization": "UNDP",
        "job_title": "Information Management Officer",
        "start_date": "2022-01",
        "end_date": "Present",
        "achievements": [
            {"id": "a1", "description": "Built Power BI dashboards for programme monitoring"},
            {"id": "a2", "description": "Mentored junior analysts on reporting hygiene"},
            {"id": "a3", "description": "Coordinated weekly team stand-ups"},
        ],
        "responsibilities": ["Managed vendor contracts", "Led digital transformation"],
    }]
    result = ensure_all_experiences(
        {"experience": []},
        experiences,
        strategy={"priority_experience": ["e1"], "keywords": ["Power BI"]},
        job={"position_title": "Data Viz Specialist", "parsed": {"keywords": [{"term": "Power BI"}]}},
        matches=[],
    )
    bullets = result["experience"][0]["bullets"]
    assert bullets[0]["text"].startswith("Built Power BI")
    assert len(bullets) == 5
    texts = [b["text"] for b in bullets]
    assert "Mentored junior analysts on reporting hygiene" in texts
    assert "Led digital transformation" in texts


def test_ensure_all_experiences_sorts_by_start_date_newest_first():
    experiences = [
        {
            "id": "old",
            "organization": "Local NGO",
            "job_title": "Intern",
            "start_date": "2016-01",
            "end_date": "2018-01",
            "responsibilities": ["Filed archives"],
        },
        {
            "id": "current",
            "organization": "FAO",
            "job_title": "Analyst",
            "start_date": "2019-06",
            "end_date": "Present",
            "responsibilities": ["Prepared yearbooks"],
        },
        {
            "id": "recent",
            "organization": "UNDP",
            "job_title": "IMO",
            "start_date": "2022-01",
            "end_date": "2023-01",
            "responsibilities": ["Built dashboards"],
        },
    ]
    result = ensure_all_experiences({"experience": []}, experiences, strategy={}, job={}, matches=[])
    assert [entry["organization"] for entry in result["experience"]] == ["UNDP", "FAO", "Local NGO"]


def test_cv_schema_strips_inline_ids_from_bullets():
    cv = GeneratedCV.model_validate({
        "summary": "IM specialist (Evidence: 387bfed5-433b-4291-b28a-720c01d5ed3c)",
        "experience": [{
            "organization": "UNDP",
            "job_title": "IMO",
            "bullets": [{
                "text": "Led IM systems (Evidence: 567fc646-37d9-4a6a-9f15-9d08cca3dd05)",
                "evidence_ids": [],
            }],
        }],
    })
    assert "Evidence" not in cv.summary
    assert cv.summary_evidence_ids == ["387bfed5-433b-4291-b28a-720c01d5ed3c"]
    assert "Evidence" not in cv.experience[0].bullets[0].text
    assert cv.experience[0].bullets[0].evidence_ids == ["567fc646-37d9-4a6a-9f15-9d08cca3dd05"]


def test_generated_cover_letter_accepts_string_paragraphs():
    letter = GeneratedCoverLetter.model_validate({
        "paragraphs": ["I would welcome the chance to contribute."],
    })
    assert letter.paragraphs[0].text.startswith("I would welcome")
    assert letter.paragraphs[0].evidence_ids == []
