"""Tests for matching payload compaction and user-facing errors."""
from __future__ import annotations

import json

from app.agents.matching import CandidateMatchingAgent, compact_matching_payload
from app.services.user_errors import public_error


def test_compact_matching_payload_sends_facts_once():
    requirements = [{"id": f"r{i}", "text": f"Requirement {i}"} for i in range(20)]
    long_text = "x" * 5000
    facts = {
        "experience": [
            {
                "entity_type": "experience",
                "entity_id": f"e{i}",
                "text": long_text,
                "verification_status": "unverified",
            }
            for i in range(30)
        ]
    }
    evidence_by_requirement = {
        req["id"]: [
            {
                "entity_type": "skill",
                "entity_id": f"s-{req['id']}-{j}",
                "text": long_text,
                "retrieval_score": 0.5 - (j * 0.01),
                "verification_status": "unverified",
            }
            for j in range(12)
        ]
        for req in requirements
    }
    evidence = [
        item
        for items in evidence_by_requirement.values()
        for item in items
    ]

    # Legacy bug size: facts * requirements would explode past the budget.
    legacy_chars = len(
        json.dumps(
            {
                "requirements": requirements,
                "evidence": evidence,
                "evidence_by_requirement": {
                    rid: items + facts["experience"]
                    for rid, items in evidence_by_requirement.items()
                },
                "structured_facts": {rid: facts for rid in evidence_by_requirement},
            }
        )
    )
    assert legacy_chars > 320_000

    payload = compact_matching_payload(
        requirements=requirements,
        evidence=evidence,
        evidence_by_requirement=evidence_by_requirement,
        structured_facts=facts,
        char_budget=320_000,
    )
    encoded = json.dumps(payload, separators=(",", ":"))
    assert len(encoded) <= 320_000
    assert "r0" not in payload["structured_facts"]
    assert len(payload["structured_facts"]["experience"]) == 30
    assert all(len(item["text"]) <= 600 for item in payload["structured_facts"]["experience"])


def test_candidate_matching_agent_normalizes_legacy_per_req_facts(monkeypatch):
    captured: dict = {}

    class FakePrompt:
        name = "candidate_matching"
        version = "v4"
        system = "sys"

        def render_user(self, **context):
            captured["payload"] = json.loads(context["payload_json"])
            return context["payload_json"]

    agent = CandidateMatchingAgent.__new__(CandidateMatchingAgent)
    agent.prompt = FakePrompt()
    agent.build_user_message(
        requirements=[{"id": "r1", "text": "Python"}],
        evidence=[],
        evidence_by_requirement={"r1": []},
        structured_facts={
            "r1": {
                "skill": [{
                    "entity_type": "skill",
                    "entity_id": "s1",
                    "text": "Python",
                    "verification_status": "verified",
                }]
            },
            "r2": {
                "skill": [{
                    "entity_type": "skill",
                    "entity_id": "s1",
                    "text": "Python",
                    "verification_status": "verified",
                }]
            },
        },
    )
    assert list(captured["payload"]["structured_facts"].keys()) == ["skill"]
    assert len(captured["payload"]["structured_facts"]["skill"]) == 1


def test_public_error_hides_provider_payload():
    raw = (
        'Matching failed: candidate_matching: 400 for https://openrouter.ai/api/v1/chat/completions: '
        '{"error":{"message":"This endpoint\'s maximum context length is 128000 tokens. '
        'However, you requested about 135194 tokens (127002 of text input, 8192 in the output)."'
    )
    message = public_error(raw)
    assert "openrouter" not in message.lower()
    assert "128000" not in message
    assert "too much detail" in message.lower() or "shorter" in message.lower()


def test_public_error_default_for_unknown():
    assert "Something went wrong" in public_error(RuntimeError("retrieval exploded"))
