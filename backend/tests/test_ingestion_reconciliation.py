"""Reconciliation keeps extracted resume content and drops empty experience shells."""

from app.llm.json_schema import openai_strict_schema
from app.schemas.agents import CareerExtractionResult, CareerReconciliationResult
from app.services.ingestion import IngestionService, build_review_proposals


def test_review_proposals_keep_extracted_content_when_model_payload_is_empty():
    extracted = [
        {
            "entity_type": "experience",
            "payload": {
                "organization": "Acme",
                "job_title": "Engineer",
                "start_date": "2020-01",
                "responsibilities": ["Built APIs"],
                "achievements": ["Cut latency by 40%"],
            },
        },
        {
            "entity_type": "achievement",
            "payload": {"description": "Cut latency by 40%", "title": ""},
        },
    ]
    model = [
        {
            "proposal_id": "p1",
            "entity_type": "experience",
            "action": "merge",
            "target_id": "exp-1",
            "target_label": "",
            "confidence": 0.9,
            "reasoning": "Same role",
            "payload": {},
        }
    ]
    existing = [
        {
            "id": "exp-1",
            "entity_type": "experience",
            "label": "Engineer at Acme",
            "organization": "Acme",
            "job_title": "Engineer",
        }
    ]

    proposals = build_review_proposals(extracted, model, existing)

    assert len(proposals) == 2
    assert proposals[0]["action"] == "merge"
    assert proposals[0]["target_id"] == "exp-1"
    assert proposals[0]["target_label"] == "Engineer at Acme"
    assert proposals[0]["payload"]["organization"] == "Acme"
    assert proposals[0]["payload"]["responsibilities"] == ["Built APIs"]
    assert proposals[1]["action"] == "create"
    assert proposals[1]["payload"]["description"] == "Cut latency by 40%"


def test_invalid_merge_target_still_keeps_extracted_payload():
    extracted = [
        {
            "entity_type": "experience",
            "payload": {"organization": "NewCo", "job_title": "Lead"},
        }
    ]
    model = [
        {
            "entity_type": "experience",
            "action": "merge",
            "target_id": "missing",
            "reasoning": "Guessed",
        }
    ]

    proposals = build_review_proposals(extracted, model, [])

    assert proposals[0]["action"] == "create"
    assert proposals[0]["target_id"] is None
    assert "invalid target discarded" in proposals[0]["reasoning"]
    assert proposals[0]["payload"]["organization"] == "NewCo"


def test_blank_experience_is_not_queued_for_review():
    result = CareerExtractionResult.model_validate(
        {
            "experiences": [
                {
                    "organization": "",
                    "job_title": "",
                    "responsibilities": [],
                    "achievements": [],
                    "projects": ["Ward rollout"],
                },
                {
                    "organization": "City Hospital",
                    "job_title": "Nurse",
                    "responsibilities": ["Medication administration"],
                },
            ],
            "achievements": ["", "Reduced falls by 20%"],
        }
    )

    items = IngestionService._build_extracted_items(None, result)
    types = [item["entity_type"] for item in items]

    assert types == ["project", "experience", "achievement"]
    assert items[1]["payload"]["organization"] == "City Hospital"
    assert items[1]["payload"]["responsibilities"] == ["Medication administration"]


def test_reconciliation_schema_does_not_require_an_empty_payload():
    schema = openai_strict_schema(CareerReconciliationResult.model_json_schema())
    proposal = schema["$defs"]["ReconciliationProposal"]
    assert "payload" not in proposal["properties"]
    encoded = str(schema)
    assert '"payload"' not in encoded
