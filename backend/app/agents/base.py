"""Base agent: prompt loading, LLM invocation, schema validation, audit (§40)."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..llm.base import LLMRequest
from ..llm.router import route_task
from ..models import AgentExecution
from ..prompts.registry import load_prompt

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class AgentContext:
    db: Session
    user_id: str
    job_id: str | None = None
    application_id: str | None = None
    workflow_run_id: str | None = None


class AgentError(Exception):
    pass


class BaseAgent:
    """All agents are independent modules coordinated by the orchestrator (§5)."""

    name: str = "base"
    task: str = "classification"  # model-routing task (§45)
    prompt_name: str = ""
    output_model: type[BaseModel] | None = None

    def __init__(self, prompt_version: str | None = None):
        self.prompt = load_prompt(self.prompt_name, prompt_version) if self.prompt_name else None

    # -- to implement -----------------------------------------------------

    def build_user_message(self, **kwargs) -> str:
        raise NotImplementedError

    # -- execution ---------------------------------------------------------

    def run(self, ctx: AgentContext, **kwargs) -> Any:
        started = time.monotonic()
        execution = AgentExecution(
            job_id=ctx.job_id,
            application_id=ctx.application_id,
            workflow_run_id=ctx.workflow_run_id,
            agent_name=self.name,
            prompt_name=self.prompt.name if self.prompt else "",
            prompt_version=self.prompt.version if self.prompt else "",
            status="RUNNING",
        )
        ctx.db.add(execution)
        ctx.db.flush()

        try:
            routed = route_task(self.task)
            execution.model = f"{routed.provider.name}:{routed.model}"
            user_message = self.build_user_message(**kwargs)
            schema = (
                self.output_model.model_json_schema() if self.output_model else None
            )
            request = LLMRequest(
                prompt_name=self.prompt.name if self.prompt else self.name,
                prompt_version=self.prompt.version if self.prompt else "",
                system=self.prompt.system if self.prompt else "",
                user=user_message,
                response_schema=schema,
            )
            response = routed.provider.generate(routed.model, request)
            result = self._parse(response.data)
            execution.status = "COMPLETED"
            execution.output = result if isinstance(result, dict) else (
                result.model_dump() if isinstance(result, BaseModel) else {"value": str(result)}
            )
            execution.output_summary = json.dumps(execution.output)[:500]
            execution.token_usage = {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            }
            execution.validation_result = {"schema_valid": True}
            return result
        except (AgentError, ValidationError) as exc:
            execution.status = "FAILED"
            execution.error = str(exc)[:2000]
            execution.validation_result = {"schema_valid": False}
            logger.warning("Agent %s failed: %s", self.name, exc)
            raise AgentError(f"{self.name}: {exc}") from exc
        except Exception as exc:  # provider/network errors
            execution.status = "FAILED"
            execution.error = str(exc)[:2000]
            logger.exception("Agent %s errored", self.name)
            raise AgentError(f"{self.name}: {exc}") from exc
        finally:
            execution.ended_at = datetime.now(timezone.utc)
            execution.duration_ms = (time.monotonic() - started) * 1000
            ctx.db.flush()

    def _parse(self, payload: dict | None) -> Any:
        if payload is None:
            raise AgentError("LLM returned no parseable JSON")
        if self.output_model is not None:
            return self.output_model.model_validate(payload)
        return payload
