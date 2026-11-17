"""run_structured(): one typed model call, answered from the ledger or recorded into it. The only importer of
pydantic_ai, so a library change touches this folder alone."""
import json
import time
from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelServerError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from app.llm.cost import cost_fields
from app.llm.factory import LlmConfig, build_model, model_settings
from app.llm.instrumentation import describe, quiet_environment
from app.llm.ledger import Ledger, LlmStop, LlmUnavailable, RecordedFailure, call_key
from app.llm.replay import replay
from app.utils.env import scrub

T = TypeVar("T", bound=BaseModel)
Mode = Literal["replay", "live"]
BREAKER_LIMIT = 5
OUT_OF_CREDIT = ("insufficient_quota", "credit_balance_exhausted")  # a 429 that retrying cannot fix
BACKOFF_SECONDS = (2.0, 8.0)  # two waits, so at most three attempts at a rate-limited or overloaded call


def _status(error: ModelAPIError) -> int | None:
    return getattr(error, "status_code", None)


def _stops_the_run(error: ModelAPIError) -> bool:
    """A rejected key, a forbidden region or no credit: every later call would fail the same way."""
    out_of_credit = any(word in f"{error.body} {error.provider_error_code}" for word in OUT_OF_CREDIT)
    refused = isinstance(error, ModelAuthenticationError | ModelQuotaExceededError) or _status(error) in (401, 403)
    return refused or out_of_credit


def _worth_retrying(error: ModelAPIError) -> bool:
    """A 429 for rate and a 5xx are temporary. A timeout is not retried: the unit is skipped and the run goes on."""
    if isinstance(error, ModelRateLimitError | ModelServerError | ModelUnavailableError):
        return True
    status = _status(error)
    return status is not None and (status == 429 or status >= 500)


def run_structured(
    cfg: LlmConfig, ledger: Ledger, *, agent: str, system_prompt: str, prompt_version: str,
    packet: dict[str, Any], schema: type[T], mode: Mode = "replay", model: Model | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """replay: ledger only, a miss raises LedgerMiss. live: replay when recorded, else call the model and record it,
    failures included. A recorded key is never sent again. Two requests at most per attempt (one retry for malformed
    output); a 429 or 5xx is retried twice with a wait; a bad key or no credit raises LlmStop."""
    settings = model_settings(cfg)
    key = call_key(cfg.model, settings, prompt_version, schema, packet)
    if mode == "replay" or ledger.get(key) is not None:
        return replay(ledger, key, schema)
    if ledger.failed_in_a_row >= BREAKER_LIMIT:
        raise LlmStop(f"circuit breaker: {BREAKER_LIMIT} live calls in a row failed or were unavailable")
    quiet_environment()
    runner: Agent[None, T] = Agent(
        model or build_model(cfg), output_type=NativeOutput(schema), system_prompt=system_prompt,
        retries=1, model_settings=cast(ModelSettings, {**settings, "timeout": cfg.request_timeout_s}),
    )
    entry: dict[str, Any] = {"key": key, "agent": agent, "model": cfg.model, "settings": settings,
                             "prompt_version": prompt_version, "packet": packet}
    try:
        result = _attempt(runner, packet, sleep)
    except UnexpectedModelBehavior as error:
        ledger.failed_in_a_row += 1
        ledger.append({**entry, "validated": False, "error": scrub(str(error))[:300], "response": None})
        raise RecordedFailure(f"the model did not give a valid answer: {scrub(str(error))}") from error
    except ModelAPIError as error:
        if _stops_the_run(error):
            raise LlmStop(f"the provider refused the request ({_status(error)}): check the key and the credit; "
                          f"{scrub(str(error))[:200]}") from error
        ledger.failed_in_a_row += 1
        # a timeout or a refused connection says nothing about the unit: not recorded
        raise LlmUnavailable(f"the model could not be reached: {scrub(str(error))}") from error
    ledger.failed_in_a_row = 0
    usage = describe(result)
    ledger.append({**entry, "validated": True, "response": result.output.model_dump(mode="json"), **usage,
                   **cost_fields(cfg.model, usage["usage"])})
    return result.output


def _attempt(runner: Agent[None, T], packet: dict[str, Any], sleep: Callable[[float], Any]) -> Any:
    for wait in (*BACKOFF_SECONDS, None):
        try:
            return runner.run_sync(json.dumps(packet, default=str), usage_limits=UsageLimits(request_limit=2))
        except ModelAPIError as error:
            if wait is None or _stops_the_run(error) or not _worth_retrying(error):
                raise
            sleep(wait)
