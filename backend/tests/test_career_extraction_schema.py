"""CareerExtractionResult accepts common LLM shape drift."""

from app.schemas.agents import CareerExtractionResult, ExtractedSkill


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
    assert all(s.category == "technical" for s in result.skills)


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
