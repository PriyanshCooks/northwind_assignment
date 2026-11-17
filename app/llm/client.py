"""run_structured(): one typed model call, answered from the ledger or recorded into it. The only importer of
pydantic_ai, so a library change touches this folder alone."""
import json
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from app.llm.factory import LlmConfig, build_model, model_settings
from app.llm.instrumentation import describe, quiet_environment
from app.llm.ledger import Ledger, LlmUnavailable, RecordedFailure, call_key
from app.llm.replay import replay

T = TypeVar("T", bound=BaseModel)
Mode = Literal["replay", "live"]


def run_structured(
    cfg: LlmConfig, ledger: Ledger, *, agent: str, system_prompt: str, prompt_version: str,
    packet: dict[str, Any], schema: type[T], mode: Mode = "replay", model: Model | None = None,
) -> T:
    """replay: ledger only, a miss raises LedgerMiss. live: replay when recorded, else call the model and record it,
    failures included. Two requests at most per call (one retry for malformed output)."""
    settings = model_settings(cfg)
    key = call_key(cfg.model, settings, prompt_version, schema, packet)
    if mode == "replay" or ledger.get(key) is not None:
        return replay(ledger, key, schema)
    quiet_environment()
    runner: Agent[None, T] = Agent(
        model or build_model(cfg), output_type=NativeOutput(schema), system_prompt=system_prompt,
        retries=1, model_settings=cast(ModelSettings, settings),
    )
    entry: dict[str, Any] = {"key": key, "agent": agent, "model": cfg.model, "settings": settings,
                             "prompt_version": prompt_version, "packet": packet}
    try:
        result = runner.run_sync(json.dumps(packet, default=str), usage_limits=UsageLimits(request_limit=2))
    except UnexpectedModelBehavior as error:
        ledger.append({**entry, "validated": False, "error": str(error)[:300], "response": None})
        raise RecordedFailure(f"the model did not give a valid answer: {error}") from error
    except ModelAPIError as error:  # a timeout or a refused connection says nothing about the unit: not recorded
        raise LlmUnavailable(f"the model could not be reached: {error}") from error
    ledger.append({**entry, "validated": True, "response": result.output.model_dump(mode="json"),
                   **describe(result)})
    return result.output
