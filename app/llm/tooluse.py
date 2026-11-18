"""run_with_tools(): a typed model call that may look things up. Same ledger rules as run_structured, and the tool
trail is recorded with the answer, so a replay shows what the model looked at without calling anything."""
import functools
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, cast

from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, NativeOutput, RunContext, Tool, ToolDefinition
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from app.llm.client import BREAKER_LIMIT, Mode, _attempt, _status, _stops_the_run
from app.llm.cost import cost_fields
from app.llm.factory import LlmConfig, build_model, model_settings
from app.llm.instrumentation import describe, quiet_environment
from app.llm.ledger import Ledger, LedgerMiss, LlmStop, LlmUnavailable, RecordedFailure, call_key
from app.utils.env import scrub

T = TypeVar("T", bound=BaseModel)
MAX_TOOL_CALLS = 5


class ToolRefused(Exception):
    """A call over the cap, repeated, or about something that does not exist. The model is told why and goes on."""


class Tools(Protocol):
    trail: list[dict[str, Any]]

    def exhausted(self) -> bool: ...

    def tools(self) -> list[Callable[..., Any]]: ...


@dataclass(frozen=True)
class Answered(Generic[T]):
    output: T
    trail: list[dict[str, Any]]


def _guarded(tool: Callable[..., Any]) -> Callable[..., Any]:
    """A refused call comes back to the model as a result saying why; it does not end the run."""

    @functools.wraps(tool)
    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except ToolRefused as why:
            return {"refused": str(why)}

    return call


def _hidden_when_spent(toolbox: Tools) -> Callable[[RunContext[None], ToolDefinition], ToolDefinition | None]:
    """Once the budget is used the tools are left out of the next request, so the model has to answer. A refusal
    message alone did not stop gpt-4o-mini from asking again until the library cap ended the run."""

    def prepare(ctx: RunContext[None], tool_def: ToolDefinition) -> ToolDefinition | None:
        return None if toolbox.exhausted() else tool_def

    return prepare


def run_with_tools(
    cfg: LlmConfig, ledger: Ledger, *, agent: str, system_prompt: str, prompt_version: str, packet: dict[str, Any],
    schema: type[T], toolbox: Tools, mode: Mode = "replay", model: Model | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Answered[T]:
    settings = model_settings(cfg)
    settings["max_tokens"] = 3 * int(settings["max_tokens"])  # a chain of steps does not fit the reviewers' 400 tokens
    names = [t.__name__ for t in toolbox.tools()]
    key = call_key(cfg.model, settings, prompt_version, schema, {"packet": packet, "tools": names})
    entry = ledger.get(key)
    if mode == "replay" and entry is None:
        raise LedgerMiss(f"no recorded answer for call {key[:12]} in {ledger.path.name}")
    if entry is not None:
        return _replayed(entry, key, schema)
    if ledger.failed_in_a_row >= BREAKER_LIMIT:
        raise LlmStop(f"circuit breaker: {BREAKER_LIMIT} live calls in a row failed or were unavailable")
    quiet_environment()
    runner: Agent[None, T] = Agent(
        model or build_model(cfg), output_type=NativeOutput(schema), system_prompt=system_prompt, retries=1,
        tools=[Tool(_guarded(t), takes_ctx=False, prepare=_hidden_when_spent(toolbox)) for t in toolbox.tools()],
        model_settings=cast(ModelSettings, {**settings, "timeout": cfg.request_timeout_s}),
    )
    record: dict[str, Any] = {"key": key, "agent": agent, "model": cfg.model, "settings": settings,
                              "prompt_version": prompt_version, "packet": packet, "tools": names}
    # the toolbox refuses calls past MAX_TOOL_CALLS with a message; this cap only stops a model that never gives up
    limits = UsageLimits(request_limit=3 * MAX_TOOL_CALLS, tool_calls_limit=3 * MAX_TOOL_CALLS)
    try:
        result = _attempt(runner, packet, sleep, limits)
    except (UnexpectedModelBehavior, UsageLimitExceeded) as error:
        ledger.failed_in_a_row += 1
        ledger.append({**record, "validated": False, "error": scrub(str(error))[:300], "response": None,
                       "trail": toolbox.trail})
        raise RecordedFailure(f"the model did not give a valid answer: {scrub(str(error))}") from error
    except ModelAPIError as error:
        if _stops_the_run(error):
            raise LlmStop(f"the provider refused the request ({_status(error)}): {scrub(str(error))[:200]}") from error
        ledger.failed_in_a_row += 1
        raise LlmUnavailable(f"the model could not be reached: {scrub(str(error))}") from error
    ledger.failed_in_a_row = 0
    usage = describe(result)
    ledger.append({**record, "validated": True, "response": result.output.model_dump(mode="json"),
                   "trail": toolbox.trail, **usage, **cost_fields(cfg.model, usage["usage"])})
    return Answered(result.output, list(toolbox.trail))


def _replayed(entry: dict[str, Any], key: str, schema: type[T]) -> Answered[T]:
    if not entry["validated"]:
        raise RecordedFailure(f"the recorded call {key[:12]} failed: {entry.get('error')}")
    try:
        return Answered(schema.model_validate(entry["response"]), entry.get("trail", []))
    except ValidationError as error:
        raise RecordedFailure(f"recorded answer {key[:12]} no longer fits the schema") from error
