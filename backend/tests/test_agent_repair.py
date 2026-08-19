"""Structured-output repair and diagnostics harness."""
from __future__ import annotations

from pydantic import BaseModel

from app.agents.base import AgentContext, AgentError, BaseAgent
from app.llm.base import LLMResponse
from app.llm.router import RoutedModel
from app.models import AgentExecution


class _Output(BaseModel):
    answer: str


class _RepairAgent(BaseAgent):
    name = "repair_harness"
    task = "classification"
    output_model = _Output
    validation_retries = 1

    def build_user_message(self, **kwargs) -> str:
        return "Return an answer."


class _SequenceProvider:
    name = "sequence"

    def __init__(self, responses: list[LLMResponse]):
        self.responses = responses
        self.requests = []

    def generate(self, model, request):
        self.requests.append(request)
        return self.responses.pop(0)


def test_agent_repairs_invalid_structured_output(db, monkeypatch):
    provider = _SequenceProvider([
        LLMResponse(text='{"wrong":"shape"}', data={"wrong": "shape"}),
        LLMResponse(text='{"answer":"fixed"}', data={"answer": "fixed"}),
    ])
    monkeypatch.setattr(
        "app.agents.base.route_task",
        lambda _: RoutedModel(provider, "test", "test"),
    )

    result = _RepairAgent().run(AgentContext(db=db, user_id="user"))

    assert result.answer == "fixed"
    assert len(provider.requests) == 2
    assert "failed schema validation" in provider.requests[1].user
    execution = (
        db.query(AgentExecution)
        .filter_by(agent_name="repair_harness")
        .order_by(AgentExecution.created_at.desc())
        .first()
    )
    assert execution.validation_result["repaired"] is True
    assert execution.validation_result["attempts"] == 2


def test_agent_records_final_invalid_response(db, monkeypatch):
    provider = _SequenceProvider([
        LLMResponse(text='{"wrong":1}', data={"wrong": 1}),
        LLMResponse(text='{"still_wrong":2}', data={"still_wrong": 2}),
    ])
    monkeypatch.setattr(
        "app.agents.base.route_task",
        lambda _: RoutedModel(provider, "test", "test"),
    )

    try:
        _RepairAgent().run(AgentContext(db=db, user_id="user"))
    except AgentError:
        pass
    else:
        raise AssertionError("invalid output should fail after bounded repair")

    execution = (
        db.query(AgentExecution)
        .filter_by(agent_name="repair_harness")
        .order_by(AgentExecution.created_at.desc())
        .first()
    )
    assert execution.status == "FAILED"
    assert "still_wrong" in execution.output["invalid_response"]
    assert execution.validation_result["attempts"] == 2
