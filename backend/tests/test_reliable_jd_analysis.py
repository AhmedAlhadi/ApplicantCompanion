"""Focused regression tests for reliable JD qualification handling."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.agents.base import AgentError
from app.agents.job_analysis import JobAnalysisAgent
from app.llm.mock_logic import mock_candidate_matching, mock_jd_analysis
from app.models import JobRequirement, RequirementMatch
from app.qualification import degree_level, evaluate_qualification_paths, overlapping_experience_years
from app.prompts.registry import load_prompt
from app.retrieval.pipeline import INDEXED_ENTITY_TYPES
from app.schemas.agents import JDAnalysisResult
from app.scoring.engine import compute_score

FIXTURES = Path(__file__).parent / "fixtures" / "jd_analysis"


def test_jd_schema_normalizes_common_provider_drift():
    payload = json.loads((FIXTURES / "schema_drift.json").read_text(encoding="utf-8"))
    result = JDAnalysisResult.model_validate(payload)
    assert result.position.job_title == "Data Platform Lead"
    assert result.position.organization == "Example Organization"
    assert result.position.location == ""
    assert result.requirements[0].importance == "CRITICAL"
    assert len(result.requirements[0].qualification_paths) == 2
    assert result.requirements[1].requirement_type == "preferred"
    assert result.responsibilities == ["Lead delivery"]
    assert [keyword.term for keyword in result.keywords] == ["Python", "data governance"]


def test_reliable_prompts_and_structured_retrieval_are_enabled():
    assert load_prompt("jd_analysis").version == "v3"
    assert load_prompt("candidate_matching").version == "v4"
    assert {"education", "certification", "language"} <= set(INDEXED_ENTITY_TYPES)


def test_job_analysis_rejects_empty_requirements():
    agent = JobAnalysisAgent()
    with pytest.raises(AgentError, match="no requirements"):
        agent._parse({"position": {"job_title": "Digital Impact Manager"}, "requirements": []})


def test_job_analysis_accepts_extracted_requirements():
    result = JobAnalysisAgent()._parse({
        "position": {"job_title": "Digital Impact Manager", "organization": "UNICEF"},
        "requirements": [{"text": "Advanced university degree", "category": "education"}],
    })
    assert len(result.requirements) == 1
    assert result.requirements[0].text == "Advanced university degree"


def test_explicit_any_of_paths_are_normalized_without_inference():
    result = JDAnalysisResult.model_validate({
        "requirements": [{
            "requirement": "Bachelor's degree or relevant experience",
            "any_of": [
                [{"type": "degree", "degree_level": "bachelor"}],
                [{"type": "experience", "years": 5}],
            ],
        }]
    })
    paths = result.requirements[0].qualification_paths
    assert [path.predicates[0].kind for path in paths] == ["degree_level", "relevant_experience"]


def test_mock_extracts_bachelor_or_experience_as_alternative_paths():
    jd = """Data Manager
Requirements:
- Bachelor's degree in information systems OR minimum 6 years of relevant experience
"""
    result = mock_jd_analysis(f"<job_description>{jd}</job_description>")
    paths = result["requirements"][0]["qualification_paths"]
    assert len(paths) == 2
    assert paths[0]["predicates"][0]["kind"] == "degree_level"
    assert paths[1]["predicates"][0]["minimum_years"] == 6.0


def test_mock_extracts_master_or_bachelor_plus_experience_paths():
    jd = """Data Platform Director
Requirements:
- Master's degree OR Bachelor's degree with at least 8 years of relevant experience
"""
    result = mock_jd_analysis(f"<job_description>{jd}</job_description>")
    paths = result["requirements"][0]["qualification_paths"]
    assert len(paths) == 2
    assert [p["kind"] for p in paths[0]["predicates"]] == ["degree_level"]
    assert [p["kind"] for p in paths[1]["predicates"]] == [
        "degree_level",
        "relevant_experience",
    ]
    assert paths[0]["predicates"][0]["minimum_level"].startswith("master")
    assert paths[1]["predicates"][0]["minimum_level"].startswith("bachelor")
    assert paths[1]["predicates"][1]["minimum_years"] == 8.0


def test_bachelor_plus_experience_satisfies_compound_alternative():
    paths = [
        {
            "label": "Master's route",
            "predicates": [{"kind": "degree_level", "minimum_level": "master"}],
        },
        {
            "label": "Bachelor plus experience route",
            "predicates": [
                {"kind": "degree_level", "minimum_level": "bachelor"},
                {
                    "kind": "relevant_experience",
                    "minimum_years": 8,
                    "terms": ["data"],
                },
            ],
        },
    ]
    facts = {
        "education": [
            {"entity_id": "ed1", "degree": "Bachelor of Science", "text": "BSc"}
        ],
        "experience": [
            {
                "entity_id": "e1",
                "text": "data platforms",
                "start_date": "2014-01",
                "end_date": "2023-12",
            }
        ],
    }
    result = evaluate_qualification_paths(paths, facts, as_of=date(2024, 1, 1))
    assert result["status"] == "MATCHED"
    assert result["selected_path_index"] == 1


def test_overlapping_relevant_periods_are_counted_once():
    years, ids = overlapping_experience_years(
        [
            {"entity_id": "e1", "text": "data platforms", "start_date": "2018-01", "end_date": "2021-12"},
            {"entity_id": "e2", "text": "data engineering", "start_date": "2020-01", "end_date": "2023-12"},
        ],
        terms=["data"],
        as_of=date(2024, 1, 1),
    )
    assert years == 6.0
    assert ids == ["e1", "e2"]


def test_bachelor_or_experience_matches_one_route_not_both():
    paths = [
        {"label": "degree", "predicates": [{"kind": "degree_level", "minimum_level": "bachelor"}]},
        {"label": "experience", "predicates": [{"kind": "relevant_experience", "minimum_years": 5, "terms": ["data"]}]},
    ]
    facts = {
        "education": [{"entity_id": "ed1", "degree": "Associate diploma", "text": "Associate diploma"}],
        "experience": [
            {"entity_id": "e1", "text": "data engineering", "start_date": "2018-01", "end_date": "2020-12"},
            {"entity_id": "e2", "text": "data platform lead", "start_date": "2020-01", "end_date": "2023-12"},
        ],
    }
    result = evaluate_qualification_paths(paths, facts, as_of=date(2024, 1, 1))
    assert result["status"] == "MATCHED"
    assert result["selected_path_index"] == 1
    assert result["path_results"][0]["status"] == "NOT_MATCHED"


def test_all_predicates_in_selected_path_are_required():
    paths = [{"predicates": [
        {"kind": "degree_level", "minimum_level": "bachelor"},
        {"kind": "relevant_experience", "minimum_years": 3, "terms": ["data"]},
    ]}]
    facts = {
        "education": [{"entity_id": "ed1", "degree": "Master of Science", "text": "Master of Science"}],
        "experience": [{"entity_id": "e1", "text": "data", "start_date": "2023-01", "end_date": "2023-12"}],
    }
    result = evaluate_qualification_paths(paths, facts, as_of=date(2024, 1, 1))
    assert result["status"] == "NOT_MATCHED"


def test_mock_and_scoring_treat_alternative_group_as_one_requirement():
    paths = [
        {"label": "degree", "predicates": [{"kind": "degree_level", "minimum_level": "bachelor"}]},
        {"label": "experience", "predicates": [{"kind": "relevant_experience", "minimum_years": 5}]},
    ]
    payload = {
        "requirements": [{"id": "r1", "text": "Bachelor or five years", "qualification_paths": paths}],
        "evidence_by_requirement": {"r1": [{
            "entity_type": "education", "entity_id": "ed1", "text": "Master of Science",
            "degree": "Master of Science", "verification_status": "verified",
        }]},
        "structured_facts": {"r1": {"education": [{
            "entity_type": "education", "entity_id": "ed1", "text": "Master of Science",
            "degree": "Master of Science",
        }]}},
    }
    matched = mock_candidate_matching(f"```json\n{json.dumps(payload)}\n```")["matches"][0]
    assert matched["status"] == "MATCHED"

    requirement = JobRequirement(
        id="r1", job_id="j1", text="Bachelor or five years", category="education",
        requirement_type="mandatory", importance="CRITICAL", keywords=[],
        qualification_paths=paths,
    )
    match = RequirementMatch(
        job_id="j1", requirement_id="r1", status="NOT_MATCHED",
        confidence=0.95, explanation="", match_kind="direct", evidence=[],
        qualification_evaluation=matched["qualification_evaluation"],
    )
    score = compute_score([requirement], [match])
    assert score["overall_score"] == 1.0
    assert score["strong_matches"] == ["Bachelor or five years"]


def test_degree_level_aliases_map_to_canonical_university_ranks():
    assert degree_level("master") == 4
    assert degree_level("bachelor") == 3
    assert degree_level("phd") == 5
    assert degree_level("advanced university degree") == 4
    assert degree_level("advanced degree") == 4
    assert degree_level("first-level university degree") == 3
    assert degree_level("first level university degree") == 3
    assert degree_level("university degree") == 3
    assert degree_level("secondary school diploma") == 1
    assert degree_level("high school diploma") == 1
    assert degree_level("PhD") == 5
    assert degree_level("بكالوريوس") == 3
    assert degree_level("ماجستير") == 4
    assert degree_level("دكتوراه") == 5
    assert degree_level("ثانوية عامة") == 1


def _three_tier_paths():
    return [
        {"label": "Master's route", "predicates": [{"kind": "degree_level", "minimum_level": "master"}]},
        {
            "label": "Bachelor plus experience route",
            "predicates": [
                {"kind": "degree_level", "minimum_level": "bachelor"},
                {"kind": "relevant_experience", "minimum_years": 7, "terms": []},
            ],
        },
        {
            "label": "Secondary plus experience route",
            "predicates": [
                {"kind": "degree_level", "minimum_level": "secondary"},
                {"kind": "relevant_experience", "minimum_years": 10, "terms": []},
            ],
        },
    ]


def test_mock_extracts_three_tier_substitution_paths():
    jd = """Programme Specialist
Requirements:
- Advanced university degree (Master's) and 5 years of relevant experience, or a first-level university degree (Bachelor's) with two additional years of relevant experience, or a secondary school diploma with 10 years of relevant experience
"""
    result = mock_jd_analysis(f"<job_description>{jd}</job_description>")
    education = next(req for req in result["requirements"] if req["category"] == "education")
    paths = education["qualification_paths"]
    assert len(paths) == 3
    assert paths[0]["predicates"][0]["minimum_level"] == "master"
    assert paths[0]["predicates"][1]["minimum_years"] == 5.0
    assert paths[1]["predicates"][0]["minimum_level"] == "bachelor"
    assert paths[1]["predicates"][1]["minimum_years"] == 7.0
    assert paths[2]["predicates"][0]["minimum_level"] == "secondary"
    assert paths[2]["predicates"][1]["minimum_years"] == 10.0


def test_additional_years_resolve_against_baseline():
    jd = """Data Lead
Requirements:
- Master's degree and 5 years of experience OR Bachelor's degree with two additional years
"""
    result = mock_jd_analysis(f"<job_description>{jd}</job_description>")
    paths = result["requirements"][0]["qualification_paths"]
    assert len(paths) == 2
    assert paths[0]["predicates"][0]["minimum_level"] == "master"
    assert paths[1]["predicates"][0]["minimum_level"] == "bachelor"
    assert paths[1]["predicates"][1]["minimum_years"] == 7.0


def test_three_tier_bachelor_plus_experience_matches_middle_path():
    facts = {
        "education": [{"entity_id": "ed1", "degree": "Bachelor of Arts", "text": "BA"}],
        "experience": [{
            "entity_id": "e1",
            "text": "programme management",
            "start_date": "2016-01",
            "end_date": "2023-12",
        }],
    }
    result = evaluate_qualification_paths(_three_tier_paths(), facts, as_of=date(2024, 1, 1))
    assert result["status"] == "MATCHED"
    assert result["selected_path_index"] == 1


def test_three_tier_secondary_plus_experience_matches_third_path():
    facts = {
        "education": [{"entity_id": "ed1", "degree": "Secondary school diploma", "text": "Secondary"}],
        "experience": [{
            "entity_id": "e1",
            "text": "operations",
            "start_date": "2010-01",
            "end_date": "2023-12",
        }],
    }
    result = evaluate_qualification_paths(_three_tier_paths(), facts, as_of=date(2024, 1, 1))
    assert result["status"] == "MATCHED"
    assert result["selected_path_index"] == 2


def test_three_tier_secondary_with_insufficient_years_does_not_match():
    facts = {
        "education": [{"entity_id": "ed1", "degree": "High school diploma", "text": "High school"}],
        "experience": [{
            "entity_id": "e1",
            "text": "operations",
            "start_date": "2020-01",
            "end_date": "2023-12",
        }],
    }
    result = evaluate_qualification_paths(_three_tier_paths(), facts, as_of=date(2024, 1, 1))
    assert result["status"] == "NOT_MATCHED"


def test_undated_experience_is_unknown_not_failed():
    paths = [{"predicates": [{"kind": "relevant_experience", "minimum_years": 5, "terms": ["digital"]}]}]
    facts = {
        "experience": [{
            "entity_id": "e1",
            "text": "Digital Impact Manager at UNICEF",
        }],
    }
    result = evaluate_qualification_paths(paths, facts, as_of=date(2024, 1, 1))
    assert result["status"] == "UNKNOWN"


def test_unparsed_degree_is_unknown_not_failed():
    paths = [{"predicates": [{"kind": "degree_level", "minimum_level": "bachelor"}]}]
    facts = {
        "education": [{"entity_id": "ed1", "degree": "Computer Science, University of Jordan", "text": "CS"}],
    }
    result = evaluate_qualification_paths(paths, facts, as_of=date(2024, 1, 1))
    assert result["status"] == "UNKNOWN"


def test_resolve_match_status_keeps_positive_model_verdict():
    from app.qualification import resolve_match_status
    assert resolve_match_status({"status": "NOT_MATCHED"}, "MATCHED") == "MATCHED"
    assert resolve_match_status({"status": "NOT_MATCHED"}, "PARTIALLY_MATCHED") == "PARTIALLY_MATCHED"
    assert resolve_match_status({"status": "MATCHED"}, "NOT_MATCHED") == "MATCHED"
    assert resolve_match_status({"status": "NOT_MATCHED"}, "UNKNOWN") == "NOT_MATCHED"
    assert resolve_match_status({"status": "UNKNOWN"}, "UNKNOWN") == "UNKNOWN"
    assert resolve_match_status({}, "TRANSFERABLE") == "TRANSFERABLE"


def test_failed_qualification_paths_do_not_wipe_evidence_match():
    paths = [{"predicates": [
        {"kind": "relevant_experience", "minimum_years": 8, "terms": ["digital transformation"]},
    ]}]
    payload = {
        "requirements": [{
            "id": "r1",
            "text": "Digital transformation experience",
            "qualification_paths": paths,
        }],
        "evidence_by_requirement": {"r1": [{
            "entity_type": "experience",
            "entity_id": "e1",
            "text": "Led digital transformation programmes at UNICEF",
            "verification_status": "needs_review",
        }]},
        "structured_facts": {"r1": {"experience": [{
            "entity_type": "experience",
            "entity_id": "e1",
            "text": "Led digital transformation programmes at UNICEF",
            "verification_status": "needs_review",
        }]}},
    }
    matched = mock_candidate_matching(f"```json\n{json.dumps(payload)}\n```")["matches"][0]
    assert matched["status"] in {"MATCHED", "PARTIALLY_MATCHED", "TRANSFERABLE"}
    assert matched["qualification_evaluation"]["status"] in {"NOT_MATCHED", "UNKNOWN"}
