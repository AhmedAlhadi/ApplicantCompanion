"""CareerExtractionResult accepts common LLM shape drift."""

from app.schemas.agents import CareerExtractionResult, ExtractedEducation, ExtractedSkill


def test_skills_accept_bare_strings_and_objects():
    result = CareerExtractionResult.model_validate(
        {
            "skills": [
                "Python",
                {"name": "SQL", "category": "technical"},
                ExtractedSkill(name="FastAPI", category="technical"),
            ]
        }
    )
    assert [s.name for s in result.skills] == ["Python", "SQL", "FastAPI"]
    assert result.skills[0].category == "uncategorized"
    assert result.skills[1].category == "technical"
    assert result.skills[2].category == "technical"


def test_achievements_accept_objects_and_strings():
    result = CareerExtractionResult.model_validate(
        {
            "achievements": [
                "Led migration",
                {
                    "description": "Contributed to platform rollout",
                    "quantified_result": "USD 500K, 50+, 700",
                },
            ],
            "experiences": [
                {
                    "organization": "Acme",
                    "job_title": "Engineer",
                    "achievements": [
                        {"description": "Shipped feature", "quantified_result": "10%"}
                    ],
                    "skills": ["Python"],
                }
            ],
        }
    )
    assert result.achievements == [
        "Led migration",
        "Contributed to platform rollout (USD 500K, 50+, 700)",
    ]
    assert result.experiences[0].achievements == ["Shipped feature (10%)"]
    assert result.experiences[0].skills == ["Python"]


def test_professional_knowledge_accepts_strings_and_objects():
    result = CareerExtractionResult.model_validate(
        {
            "professional_knowledge": [
                "logistics",
                {
                    "name": "subscription billing",
                    "kind": "process",
                    "depth": "applied",
                    "organization_hint": "CloudCo",
                },
            ],
            "experiences": [
                {
                    "organization": "ShipCo",
                    "job_title": "Developer",
                    "domains": ["freight"],
                    "professional_knowledge": ["warehousing"],
                }
            ],
        }
    )
    assert [item.name for item in result.professional_knowledge] == ["logistics", "subscription billing"]
    assert result.professional_knowledge[1].kind == "process"
    assert result.experiences[0].professional_knowledge[0].name == "warehousing"


def test_extracted_dates_normalize_month_names():
    result = CareerExtractionResult.model_validate(
        {
            "education": [
                {
                    "institution": "Lebanese International University",
                    "degree": "BSC",
                    "field_of_study": "INFORMATION TECHNOLOGY",
                    "start_date": "AUGUST 2013",
                    "end_date": "Present",
                }
            ],
            "experiences": [
                {
                    "organization": "Acme",
                    "job_title": "Engineer",
                    "start_date": "January 2021",
                    "end_date": "current",
                }
            ],
            "certifications": [{"name": "AWS", "issue_date": "June 2020"}],
        }
    )
    assert result.education[0].start_date == "2013-08"
    assert result.education[0].end_date == ""
    assert result.experiences[0].start_date == "2021-01"
    assert result.experiences[0].end_date == ""
    assert result.certifications[0].issue_date == "2020-06"
    assert len(ExtractedEducation.model_validate({"start_date": "AUGUST 2013"}).start_date) <= 10
